"""SmartRecruiters public postings API: full descriptions, structured locations, no key.

    GET https://api.smartrecruiters.com/v1/companies/{board}/postings          (list)
    GET https://api.smartrecruiters.com/v1/companies/{board}/postings/{id}     (detail)

Unlike Greenhouse, the list carries no description, so each posting worth keeping costs a
second request. The list does carry the title and an ISO country code, so `fetch_postings`
filters on those first and only then spends a request per survivor: on a 4,822-posting
board that is about 140 detail calls instead of 4,822.

This is the source that reaches large non-tech employers, who are otherwise missing from
the sample.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from pipeline.http import get_json
from pipeline.ingest.posting import RawPosting
from pipeline.ingest.text import html_to_text
from pipeline.taxonomy import is_relevant_title, load_countries

log = logging.getLogger(__name__)

URL = "https://api.smartrecruiters.com/v1/companies/{board}/postings"

PAGE_SIZE = 100
"""The API's maximum; asking for more silently returns 100."""

MAX_PAGES = 60
"""Enough for the largest board seen (Bosch, ~4,800 postings). A board that exceeds this
is logged rather than paged forever, since one company should not dominate a daily run."""

DESCRIPTION_SECTIONS = ("jobDescription", "qualifications", "additionalInformation")
"""`companyDescription` is deliberately excluded: it is the "About us" blurb, and postings
that consist of one taught us that it costs a model call to learn nothing."""


def fetch_postings(client: httpx.Client, board: str) -> list[dict[str, Any]]:
    """Full detail for every posting on a board that is plausibly in scope."""
    wanted = [item for item in _list_postings(client, board) if _worth_fetching(item)]
    postings = []
    for item in wanted:
        detail = get_json(
            client, f"{URL.format(board=board)}/{item['id']}", label=f"SmartRecruiters {board}"
        )
        postings.append(detail)
    return postings


def survey(client: httpx.Client, board: str) -> tuple[int, int]:
    """How many postings a board lists, and how many are worth storing.

    Used when probing candidate boards, where descriptions are not needed: the list alone
    carries the title and country that decide scope, so a survey costs a handful of
    requests instead of one per posting.
    """
    items = _list_postings(client, board)
    return len(items), sum(1 for item in items if _worth_fetching(item))


def parse_posting(posting: dict[str, Any], company: str) -> RawPosting:
    location = posting.get("location") or {}
    return RawPosting(
        source="smartrecruiters",
        source_id=str(posting["id"]),
        url=posting["postingUrl"],
        title=posting["name"],
        company=company,
        location_raw=location.get("fullLocation") or None,
        country=_country(location),
        description_text=_description(posting),
        posted_at=posting.get("releasedDate"),
    )


def _list_postings(client: httpx.Client, board: str) -> list[dict[str, Any]]:
    """Every posting's summary, one page at a time."""
    items: list[dict[str, Any]] = []
    for page in range(MAX_PAGES):
        data = get_json(
            client,
            URL.format(board=board),
            params={"limit": PAGE_SIZE, "offset": page * PAGE_SIZE},
            label=f"SmartRecruiters {board}",
        )
        items.extend(data.get("content") or [])
        if len(items) >= int(data.get("totalFound") or 0):
            return items
    log.warning("SmartRecruiters %s: stopped after the first %d postings", board, len(items))
    return items


def _worth_fetching(item: dict[str, Any]) -> bool:
    """Whether a summary justifies a second request for its description."""
    country = ((item.get("location") or {}).get("country") or "").upper()
    return country in load_countries() and is_relevant_title(item.get("name") or "")


def _country(location: dict[str, Any]) -> str | None:
    """The ISO code the API states, when it is one of the curated countries."""
    code = (location.get("country") or "").upper()
    return code if code in load_countries() else None


def _description(posting: dict[str, Any]) -> str:
    sections = (posting.get("jobAd") or {}).get("sections") or {}
    parts = [(sections.get(name) or {}).get("text") or "" for name in DESCRIPTION_SECTIONS]
    return html_to_text("\n".join(part for part in parts if part))

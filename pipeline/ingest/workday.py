"""Workday career sites: full descriptions, no key, and where large employers post.

    POST https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    GET  https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}

These sites invite crawling - their robots.txt publishes a sitemap and allows the career
path - which matters because the employers on them (industrial, pharma, retail, banks)
are exactly the ones missing from Greenhouse and Ashby.

A board is identified by three parts, written in companies.yaml as `tenant/wd/site`:
the tenant, the Workday cluster it lives in (`wd1`, `wd3`, `wd5`...) and the career site
name. All three appear in the careers URL a company links to.

Two requests decide the cost of a board. The first reads the location facet and keeps only
the countries the taxonomy covers, which on a 2,000-posting board leaves a few hundred;
titles are then filtered from the listing, so a description is fetched only for a posting
that would actually be stored.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from pipeline.http import get_json, post_json
from pipeline.ingest.posting import RawPosting
from pipeline.ingest.text import html_to_text
from pipeline.taxonomy import is_relevant_title, resolve_country

log = logging.getLogger(__name__)

HOST = "https://{tenant}.{cluster}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"

PAGE_SIZE = 20
"""The API's maximum; a larger `limit` returns an error rather than more rows."""

MAX_PAGES = 100
"""2,000 postings. The largest board seen in our countries holds about 1,500, and one
company should not be able to make a daily run unbounded."""

COUNTRY_FACETS = ("locationHierarchy1", "Location_Country")
"""Parameter names employers use for the country facet. Workday lets each one configure its
own facets, so this is a best effort: NVIDIA nests countries under `locationHierarchy1`,
GSK exposes `Location_Country`, and AstraZeneca offers no country level at all. When none
matches, the board is listed unfiltered and each posting states its own country."""


def board_url(board: str) -> str:
    """Base URL for a `tenant/cluster/site` board identifier."""
    parts = board.split("/")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"Workday board must be 'tenant/cluster/site', got {board!r}")
    tenant, cluster, site = parts
    return HOST.format(tenant=tenant, cluster=cluster, site=site)


def fetch_postings(client: httpx.Client, board: str) -> list[dict[str, Any]]:
    """Full detail for every posting on a board that is plausibly in scope."""
    base = board_url(board)
    label = f"Workday {board}"
    wanted = [item for item in _list_postings(client, base, label) if _worth_fetching(item)]
    postings = []
    for item in wanted:
        detail = get_json(client, base + item["externalPath"], label=label)
        postings.append(detail.get("jobPostingInfo") or {})
    return postings


def survey(client: httpx.Client, board: str) -> tuple[int, int]:
    """How many postings a board lists in our countries, and how many are worth storing.

    Used when probing candidate boards: no description is fetched, because the listing
    already carries the title and the country filter is applied by the server.
    """
    base = board_url(board)
    items = _list_postings(client, base, f"Workday {board}")
    return len(items), sum(1 for item in items if _worth_fetching(item))


def parse_posting(posting: dict[str, Any], company: str) -> RawPosting:
    location = posting.get("location") or ""
    country_name = (posting.get("country") or {}).get("descriptor") or ""
    return RawPosting(
        source="workday",
        source_id=str(posting["id"]),
        url=posting["externalUrl"],
        title=posting["title"],
        company=company,
        location_raw=location or None,
        # The stated country wins: "Germany, Remote" and "Remote" both resolve from it.
        country=resolve_country(country_name) or resolve_country(location),
        description_text=html_to_text(posting.get("jobDescription") or ""),
        posted_at=posting.get("startDate"),
    )


def _list_postings(client: httpx.Client, base: str, label: str) -> list[dict[str, Any]]:
    """Every posting the board lists, narrowed to our countries where the board allows it."""
    facets = _country_filter(client, base, label)
    items: list[dict[str, Any]] = []
    total = 0
    for page in range(MAX_PAGES):
        data = post_json(
            client,
            f"{base}/jobs",
            label=label,
            json_body={
                "appliedFacets": facets,
                "limit": PAGE_SIZE,
                "offset": page * PAGE_SIZE,
                "searchText": "",
            },
        )
        batch = data.get("jobPostings") or []
        items.extend(batch)
        # Only the first page reports how many there are; later pages say `total: 0`, so
        # trusting it every time would end the run after two pages.
        total = total or int(data.get("total") or 0)
        if not batch or len(items) >= total:
            return items
    log.warning("%s: stopped after the first %d postings", label, len(items))
    return items


def _country_filter(client: httpx.Client, base: str, label: str) -> dict[str, list[str]]:
    """`appliedFacets` narrowing the board to our countries, or empty if it cannot.

    Facet ids are per employer, so they are read off the board rather than configured.
    Narrowing here is only an economy - it saves listing jobs in countries we do not
    cover - so a board without a usable country facet is listed in full instead.
    """
    data = post_json(
        client,
        f"{base}/jobs",
        label=label,
        json_body={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
    )
    for facet in _facets(data):
        if facet.get("facetParameter") not in COUNTRY_FACETS:
            continue
        ids = [
            value["id"]
            for value in facet.get("values") or []
            if resolve_country(value.get("descriptor") or "")
        ]
        if ids:
            return {facet["facetParameter"]: ids}
    log.info("%s: no country facet, listing every posting", label)
    return {}


def _facets(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Every facet, whether the board puts it at the top level or inside a group."""
    facets = data.get("facets") or []
    return facets + [group for facet in facets for group in facet.get("values") or []]


def _worth_fetching(item: dict[str, Any]) -> bool:
    """Whether a listing justifies a second request for its description."""
    return bool(item.get("externalPath")) and is_relevant_title(item.get("title") or "")

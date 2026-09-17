"""Greenhouse public job board API: full descriptions, free-text locations, no key.

GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from pipeline.ingest.http import get_json
from pipeline.ingest.posting import RawPosting
from pipeline.ingest.text import html_to_text
from pipeline.taxonomy import resolve_country

URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"

# Words that describe how a job is worked rather than where: "Hybrid", "In-Office", "N/A".
_WORK_ARRANGEMENT_WORDS = frozenset(
    "a and anywhere distributed flexible hybrid in n na office on onsite or remote site".split()
)
_WORDS = re.compile(r"[a-z]+")


def fetch_jobs(client: httpx.Client, board: str) -> list[dict[str, Any]]:
    """Every job on a company's Greenhouse board, with descriptions."""
    data = get_json(
        client, URL.format(board=board), params={"content": "true"}, label=f"Greenhouse {board}"
    )
    return data["jobs"]


def parse_job(job: dict[str, Any], company: str) -> RawPosting:
    location = ((job.get("location") or {}).get("name") or "").strip()
    return RawPosting(
        source="greenhouse",
        source_id=str(job["id"]),
        url=job["absolute_url"],
        title=job["title"],
        company=company,
        location_raw=location or None,
        country=_country(job, location),
        description_text=html_to_text(job.get("content") or "", escaped=True),
        posted_at=job.get("first_published") or job.get("updated_at"),
    )


def _country(job: dict[str, Any], location: str) -> str | None:
    """Country from the location; office names are consulted only when it names no place.

    Some boards put the work arrangement in the location ("Hybrid") and the city in the
    offices. A location that does name a place ("Toronto", "Remote India") is never
    overridden by an office elsewhere.
    """
    if not all(word in _WORK_ARRANGEMENT_WORDS for word in _WORDS.findall(location.lower())):
        return resolve_country(location)
    return resolve_country(", ".join(office["name"] for office in job.get("offices") or []))

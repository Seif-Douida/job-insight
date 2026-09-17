"""Lever public postings API: full descriptions split into sections, ISO country codes, no key.

GET https://api.lever.co/v0/postings/{board}?mode=json
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from pipeline.ingest.http import get_json
from pipeline.ingest.posting import RawPosting
from pipeline.ingest.text import html_to_text
from pipeline.taxonomy import resolve_country

URL = "https://api.lever.co/v0/postings/{board}"


def fetch_postings(client: httpx.Client, board: str) -> list[dict[str, Any]]:
    """Every posting on a company's Lever board."""
    return get_json(
        client, URL.format(board=board), params={"mode": "json"}, label=f"Lever {board}"
    )


def parse_posting(posting: dict[str, Any], company: str) -> RawPosting:
    location = (posting.get("categories") or {}).get("location")
    country = posting.get("country")
    return RawPosting(
        source="lever",
        source_id=posting["id"],
        url=posting["hostedUrl"],
        title=posting["text"],
        company=company,
        location_raw=location,
        country=country.upper() if country else resolve_country(location),
        description_text=_description(posting),
        posted_at=_from_epoch_ms(posting.get("createdAt")),
    )


def _description(posting: dict[str, Any]) -> str:
    """Lever splits a posting into an intro, titled lists and closing text; rejoin them."""
    sections = [posting.get("descriptionPlain") or ""]
    for section in posting.get("lists") or []:
        sections.append(f"{section.get('text', '')}\n{html_to_text(section.get('content') or '')}")
    sections.append(posting.get("additionalPlain") or "")
    return "\n\n".join(section.strip() for section in sections if section.strip())


def _from_epoch_ms(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value / 1000, tz=UTC) if value else None

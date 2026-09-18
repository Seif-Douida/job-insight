"""Ingestion units: fetch from one source, keep in-scope postings, store them.

Each function covers one retryable unit of work (one company board, one Adzuna query,
one JSearch query). The caller owns the connection and commits the transaction.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from typing import Any

import httpx
import psycopg

from pipeline.ingest import adzuna, ashby, greenhouse, jsearch, lever, smartrecruiters, workday
from pipeline.ingest.posting import RawPosting
from pipeline.ingest.store import upsert_postings
from pipeline.taxonomy import (
    OTHER_REGION,
    AdzunaMarket,
    Company,
    Country,
    Role,
    is_relevant_title,
)

log = logging.getLogger(__name__)

Item = dict[str, Any]
BoardFetcher = Callable[[httpx.Client, str], list[Item]]
BoardParser = Callable[[Item, str], RawPosting]

BOARD_SOURCES: dict[str, tuple[BoardFetcher, BoardParser]] = {
    "greenhouse": (greenhouse.fetch_jobs, greenhouse.parse_job),
    "lever": (lever.fetch_postings, lever.parse_posting),
    "ashby": (ashby.fetch_jobs, ashby.parse_job),
    "smartrecruiters": (smartrecruiters.fetch_postings, smartrecruiters.parse_posting),
    "workday": (workday.fetch_postings, workday.parse_posting),
}


@dataclass(frozen=True)
class IngestResult:
    """What one unit of ingestion did; returned to Airflow as the task result."""

    label: str
    fetched: int
    invalid: int
    kept: int
    inserted: int
    updated: int

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


def in_scope(posting: RawPosting) -> bool:
    """Stored only if it is in a curated region and plausibly a curated role."""
    return posting.region != OTHER_REGION and is_relevant_title(posting.title)


def parse_items(
    items: Iterable[Item], parse: Callable[[Item], RawPosting]
) -> tuple[list[RawPosting], int]:
    """Parse source items, skipping and counting malformed ones instead of failing the batch."""
    postings: list[RawPosting] = []
    invalid = 0
    for item in items:
        try:
            postings.append(parse(item))
        except (KeyError, TypeError, ValueError) as error:  # pydantic errors are ValueErrors
            invalid += 1
            log.warning("Skipping malformed item %s: %s", item.get("id", "?"), error)
    return postings, invalid


def ingest_board(
    company: Company, *, client: httpx.Client, conn: psycopg.Connection
) -> IngestResult:
    """Read one company's job board."""
    fetch, parse = BOARD_SOURCES[company.ats]
    items = fetch(client, company.board)
    postings, invalid = parse_items(items, lambda item: parse(item, company.name))
    return _store(f"{company.ats}:{company.board}", len(items), invalid, postings, conn)


def ingest_adzuna(
    market: AdzunaMarket,
    role: Role,
    *,
    client: httpx.Client,
    conn: psycopg.Connection,
    app_id: str,
    app_key: str,
    max_days_old: int = 8,
    pause_seconds: float = adzuna.PAUSE_SECONDS,
) -> IngestResult:
    """Search one Adzuna market for one role, stopping early when results run out."""
    items: list[Item] = []
    for page in range(1, market.pages + 1):
        results = adzuna.fetch_page(
            client,
            market,
            role.search,
            page,
            app_id=app_id,
            app_key=app_key,
            max_days_old=max_days_old,
        )
        items.extend(results)
        time.sleep(pause_seconds)
        if len(results) < adzuna.RESULTS_PER_PAGE:
            break
    postings, invalid = parse_items(items, lambda item: adzuna.parse_result(item, market))
    return _store(f"adzuna:{market.market}:{role.slug}", len(items), invalid, postings, conn)


def ingest_jsearch(
    country: Country,
    role: Role,
    *,
    client: httpx.Client,
    conn: psycopg.Connection,
    api_key: str,
    date_posted: str = "week",
) -> IngestResult:
    """Search JSearch for one role in one country (a single call)."""
    items = jsearch.fetch_jobs(
        client, country, role.search, api_key=api_key, date_posted=date_posted
    )
    postings, invalid = parse_items(items, lambda item: jsearch.parse_job(item, country.code))
    return _store(
        f"jsearch:{country.code.lower()}:{role.slug}", len(items), invalid, postings, conn
    )


def _store(
    label: str, fetched: int, invalid: int, postings: list[RawPosting], conn: psycopg.Connection
) -> IngestResult:
    kept = [posting for posting in postings if in_scope(posting)]
    counts = upsert_postings(conn, kept)
    result = IngestResult(label, fetched, invalid, len(kept), counts.inserted, counts.updated)
    log.info("%s", result)
    return result

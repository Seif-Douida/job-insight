"""Adzuna search API: broad US/UK/EU coverage with salaries, but 500-character excerpts.

    GET https://api.adzuna.com/v1/api/jobs/{market}/search/{page}

The API key travels in the query string; pipeline.http keeps it out of logs and errors.
"""

from __future__ import annotations

from typing import Any

import httpx

from pipeline.http import get_json
from pipeline.ingest.posting import RawPosting
from pipeline.ingest.text import html_to_text
from pipeline.taxonomy import AdzunaMarket

URL = "https://api.adzuna.com/v1/api/jobs/{market}/search/{page}"
RESULTS_PER_PAGE = 50
MONTHLY_CALL_LIMIT = 1000

PAUSE_SECONDS = 2.5
"""Wait after each call, so a single worker stays under 25 calls a minute."""


def fetch_page(
    client: httpx.Client,
    market: AdzunaMarket,
    phrase: str,
    page: int,
    *,
    app_id: str,
    app_key: str,
    max_days_old: int,
) -> list[dict[str, Any]]:
    """One page of recent postings whose title contains `phrase`."""
    data = get_json(
        client,
        URL.format(market=market.market, page=page),
        params={
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": RESULTS_PER_PAGE,
            "what_phrase": phrase,
            "title_only": phrase,
            "max_days_old": max_days_old,
            "content-type": "application/json",
        },
        label=f"Adzuna {market.market} {phrase!r} page {page}",
    )
    return data["results"]


def parse_result(result: dict[str, Any], market: AdzunaMarket) -> RawPosting:
    salary_min, salary_max = result.get("salary_min"), result.get("salary_max")
    return RawPosting(
        source="adzuna",
        source_id=str(result["id"]),
        url=result["redirect_url"],
        title=html_to_text(result["title"]),
        company=(result.get("company") or {}).get("display_name"),
        location_raw=(result.get("location") or {}).get("display_name"),
        country=market.country,
        description_text=html_to_text(result.get("description") or ""),
        posted_at=result.get("created"),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=market.currency if salary_min or salary_max else None,
        salary_is_predicted=str(result.get("salary_is_predicted")) == "1",
    )

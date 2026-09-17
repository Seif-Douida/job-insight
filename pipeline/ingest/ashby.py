"""Ashby public job board API: full plain-text descriptions, structured addresses and pay.

GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true
"""

from __future__ import annotations

from typing import Any

import httpx

from pipeline.ingest.http import get_json
from pipeline.ingest.posting import RawPosting
from pipeline.taxonomy import resolve_country

URL = "https://api.ashbyhq.com/posting-api/job-board/{board}"


def fetch_jobs(client: httpx.Client, board: str) -> list[dict[str, Any]]:
    """Every listed job on a company's Ashby board, with compensation."""
    data = get_json(
        client,
        URL.format(board=board),
        params={"includeCompensation": "true"},
        label=f"Ashby {board}",
    )
    return [job for job in data["jobs"] if job.get("isListed", True)]


def parse_job(job: dict[str, Any], company: str) -> RawPosting:
    address = (job.get("address") or {}).get("postalAddress") or {}
    salary_min, salary_max, currency = _yearly_salary(job.get("compensation"))
    return RawPosting(
        source="ashby",
        source_id=job["id"],
        url=job["jobUrl"],
        title=job["title"],
        company=company,
        location_raw=job.get("location"),
        country=resolve_country(address.get("addressCountry"))
        or resolve_country(job.get("location")),
        description_text=job.get("descriptionPlain") or "",
        posted_at=job.get("publishedAt"),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency,
    )


def _yearly_salary(
    compensation: dict[str, Any] | None,
) -> tuple[float | None, float | None, str | None]:
    """The stated yearly base salary range, when the posting publishes one."""
    for component in (compensation or {}).get("summaryComponents") or []:
        if component.get("compensationType") == "Salary" and component.get("interval") == "1 YEAR":
            return (
                component.get("minValue"),
                component.get("maxValue"),
                component.get("currencyCode"),
            )
    return None, None, None

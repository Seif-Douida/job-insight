"""JSearch search API (OpenWeb Ninja): Google for Jobs listings, used for Gulf coverage.

    GET https://api.openwebninja.com/jsearch/search-v2    header: x-api-key

Text length depends on the original publisher: LinkedIn or GulfTalent give full
descriptions, many aggregators a ~500-character snippet, which RawPosting.text_quality
classifies as an excerpt. Salaries are not read: responses carry no currency.
"""

from __future__ import annotations

from typing import Any

import httpx

from pipeline.http import get_json
from pipeline.ingest.posting import RawPosting
from pipeline.taxonomy import Country

URL = "https://api.openwebninja.com/jsearch/search-v2"
MONTHLY_CALL_LIMIT = 200


def fetch_jobs(
    client: httpx.Client,
    country: Country,
    phrase: str,
    *,
    api_key: str,
    date_posted: str = "week",
) -> list[dict[str, Any]]:
    """First page (up to 10) of recent postings for `phrase` in `country`, in English."""
    data = get_json(
        client,
        URL,
        params={
            "query": f"{phrase} in {country.name}",
            "country": country.code.lower(),
            "language": "en",
            "date_posted": date_posted,
        },
        headers={"x-api-key": api_key},
        label=f"JSearch {country.code} {phrase!r}",
    )
    return (data.get("data") or {}).get("jobs") or []


def parse_job(job: dict[str, Any], queried_country: str) -> RawPosting:
    """`queried_country` fills in when the listing omits its own country."""
    return RawPosting(
        source="jsearch",
        source_id=job["job_id"],
        url=job.get("job_apply_link") or job["job_google_link"],
        title=job["job_title"],
        company=job.get("employer_name"),
        location_raw=job.get("job_location"),
        country=(job.get("job_country") or queried_country).upper(),
        description_text=job.get("job_description") or "",
        posted_at=job.get("job_posted_at_datetime_utc"),
    )

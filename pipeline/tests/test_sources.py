"""Source clients against real API responses recorded in tests/fixtures.

Each client is checked for the request it sends and for how it parses the response.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from pipeline.ingest import adzuna, ashby, greenhouse, jsearch, lever
from pipeline.ingest.http import SourceError
from pipeline.taxonomy import adzuna_markets, get_country, jsearch_countries, load_roles

GB_MARKET = get_country("GB").adzuna
WEEKLY_RUNS_PER_MONTH = 52 / 12


def recording_client(payload: Any, requests: list[httpx.Request]) -> httpx.Client:
    """A client that answers every request with `payload` and records the requests."""

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def failing_client(status: int) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status)))


def job_with_id(jobs: list[dict[str, Any]], job_id: int) -> dict[str, Any]:
    return next(job for job in jobs if job["id"] == job_id)


# --- Greenhouse ------------------------------------------------------------------------


def test_greenhouse_fetch_requests_descriptions(load_fixture: Callable[[str], Any]) -> None:
    requests: list[httpx.Request] = []
    with recording_client(load_fixture("greenhouse_jobs.json"), requests) as client:
        jobs = greenhouse.fetch_jobs(client, "stripe")
    assert requests[0].url.path == "/v1/boards/stripe/jobs"
    assert requests[0].url.params["content"] == "true"
    assert len(jobs) == 5


def test_greenhouse_parse_decodes_html_and_resolves_location(
    load_fixture: Callable[[str], Any],
) -> None:
    job = job_with_id(load_fixture("greenhouse_jobs.json")["jobs"], 8189909)
    posting = greenhouse.parse_job(job, "Stripe")
    assert (posting.source_id, posting.title, posting.country) == (
        "8189909",
        "Data Analyst, NYC",
        "US",
    )
    assert posting.text_quality == "full"
    assert "<" not in posting.description_text and "&lt;" not in posting.description_text
    assert posting.posted_at is not None and posting.posted_at.tzinfo is not None


def test_greenhouse_location_outside_taxonomy_stays_unresolved(
    load_fixture: Callable[[str], Any],
) -> None:
    job = job_with_id(load_fixture("greenhouse_jobs.json")["jobs"], 5416444)  # "Canada"
    assert greenhouse.parse_job(job, "Stripe").country is None


@pytest.mark.parametrize(
    ("location", "offices", "expected"),
    [
        ("N/A", ["Ireland Locations"], "IE"),
        ("Hybrid", ["London, United Kingdom"], "GB"),  # Cloudflare's board works this way
        ("In-Office", ["Austin, TX", "New York, NY"], "US"),
        ("Distributed; Hybrid", ["Berlin"], "DE"),
        ("Remote India", ["Austin, TX"], None),  # names a place: offices are not consulted
        ("Toronto", ["New York, NY"], None),
    ],
)
def test_greenhouse_uses_offices_only_when_location_names_no_place(
    location: str, offices: list[str], expected: str | None
) -> None:
    job = {
        "id": 1,
        "absolute_url": "https://example.com/1",
        "title": "Data Engineer",
        "location": {"name": location},
        "offices": [{"name": name} for name in offices],
    }
    assert greenhouse.parse_job(job, "Acme").country == expected


# --- Lever -----------------------------------------------------------------------------


def test_lever_fetch_requests_json_mode(load_fixture: Callable[[str], Any]) -> None:
    requests: list[httpx.Request] = []
    with recording_client(load_fixture("lever_postings.json"), requests) as client:
        postings = lever.fetch_postings(client, "spotify")
    assert requests[0].url.path == "/v0/postings/spotify"
    assert requests[0].url.params["mode"] == "json"
    assert len(postings) == 4


def test_lever_parse_uses_country_code_and_rejoins_sections(
    load_fixture: Callable[[str], Any],
) -> None:
    postings = [
        lever.parse_posting(item, "Spotify") for item in load_fixture("lever_postings.json")
    ]
    assert [posting.country for posting in postings] == ["US", "US", "GB", "VN"]
    data_scientist = postings[0]
    assert data_scientist.title.startswith("Data Scientist")
    assert data_scientist.url.startswith("https://jobs.lever.co/spotify/")
    assert data_scientist.text_quality == "full"
    assert "<li>" not in data_scientist.description_text
    assert data_scientist.posted_at is not None and data_scientist.posted_at.year >= 2020


# --- Ashby -----------------------------------------------------------------------------


def test_ashby_fetch_includes_pay_and_skips_unlisted_jobs(
    load_fixture: Callable[[str], Any],
) -> None:
    payload = load_fixture("ashby_jobs.json")
    payload["jobs"][0]["isListed"] = False
    requests: list[httpx.Request] = []
    with recording_client(payload, requests) as client:
        jobs = ashby.fetch_jobs(client, "openai")
    assert requests[0].url.params["includeCompensation"] == "true"
    assert len(jobs) == 3


def test_ashby_parse_reads_country_and_yearly_salary(load_fixture: Callable[[str], Any]) -> None:
    posting = ashby.parse_job(load_fixture("ashby_jobs.json")["jobs"][0], "OpenAI")
    assert (posting.title, posting.country, posting.text_quality) == ("Data Engineer", "US", "full")
    assert (posting.salary_min, posting.salary_max, posting.salary_currency) == (
        235000,
        385000,
        "USD",
    )


# --- Adzuna ----------------------------------------------------------------------------


def test_adzuna_fetch_searches_titles_for_the_role_phrase(
    load_fixture: Callable[[str], Any],
) -> None:
    requests: list[httpx.Request] = []
    with recording_client(load_fixture("adzuna_search_gb.json"), requests) as client:
        results = adzuna.fetch_page(
            client, GB_MARKET, "data engineer", 2, app_id="id", app_key="key", max_days_old=8
        )
    url = requests[0].url
    assert url.path == "/v1/api/jobs/gb/search/2"
    assert (url.params["what_phrase"], url.params["title_only"]) == (
        "data engineer",
        "data engineer",
    )
    assert (url.params["results_per_page"], url.params["max_days_old"]) == ("50", "8")
    assert len(results) == 5


def test_adzuna_errors_never_expose_credentials() -> None:
    with failing_client(401) as client, pytest.raises(SourceError) as raised:
        adzuna.fetch_page(
            client,
            GB_MARKET,
            "data engineer",
            1,
            app_id="my-id",
            app_key="my-secret",
            max_days_old=8,
        )
    message = str(raised.value)
    assert "401" in message
    assert "my-secret" not in message and "my-id" not in message
    assert raised.value.__suppress_context__  # the httpx error, which holds the URL, is dropped


def test_adzuna_parse_marks_excerpt_and_stated_salary(load_fixture: Callable[[str], Any]) -> None:
    posting = adzuna.parse_result(load_fixture("adzuna_search_gb.json")["results"][0], GB_MARKET)
    assert (posting.source_id, posting.company, posting.country) == ("5878827773", "Ocho", "GB")
    assert (posting.salary_min, posting.salary_currency, posting.salary_is_predicted) == (
        45000,
        "GBP",
        False,
    )
    assert posting.text_quality == "excerpt"


# --- JSearch ---------------------------------------------------------------------------


def test_jsearch_fetch_queries_the_country_in_english(load_fixture: Callable[[str], Any]) -> None:
    requests: list[httpx.Request] = []
    with recording_client(load_fixture("jsearch_search_ae.json"), requests) as client:
        jobs = jsearch.fetch_jobs(client, get_country("AE"), "data engineer", api_key="secret")
    request = requests[0]
    assert request.headers["x-api-key"] == "secret"
    assert request.url.params["query"] == "data engineer in United Arab Emirates"
    assert (request.url.params["country"], request.url.params["language"]) == ("ae", "en")
    assert len(jobs) == 4


def test_jsearch_parse_classifies_snippets_as_excerpts(load_fixture: Callable[[str], Any]) -> None:
    jobs = load_fixture("jsearch_search_ae.json")["data"]["jobs"]
    postings = [jsearch.parse_job(job, "AE") for job in jobs]
    assert [posting.country for posting in postings] == ["AE"] * 4  # one omits it; query fills in
    assert [posting.text_quality for posting in postings] == ["excerpt", "excerpt", "full", "full"]


# --- free-tier budgets -----------------------------------------------------------------


def test_adzuna_config_fits_the_free_monthly_quota() -> None:
    """Worst case: every query uses all its pages. 20% headroom for retries and manual runs."""
    calls_per_run = len(load_roles()) * sum(market.pages for market in adzuna_markets())
    assert calls_per_run * WEEKLY_RUNS_PER_MONTH <= adzuna.MONTHLY_CALL_LIMIT * 0.8


def test_jsearch_config_fits_the_free_monthly_quota() -> None:
    calls_per_run = len(load_roles()) * len(jsearch_countries())
    assert calls_per_run * WEEKLY_RUNS_PER_MONTH <= jsearch.MONTHLY_CALL_LIMIT * 0.8

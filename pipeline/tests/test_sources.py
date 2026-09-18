"""Source clients against real API responses recorded in tests/fixtures.

Each client is checked for the request it sends and for how it parses the response.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from pipeline.http import HttpError
from pipeline.ingest import adzuna, ashby, greenhouse, jsearch, lever, smartrecruiters, workday
from pipeline.taxonomy import (
    adzuna_markets,
    get_country,
    is_relevant_title,
    jsearch_countries,
    load_roles,
)

GB_MARKET = get_country("GB").adzuna
WEEKLY_RUNS_PER_MONTH = 52 / 12
JSEARCH_RUNS_PER_MONTH = 2  # ingest_jsearch runs on the 1st and the 15th


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
    with failing_client(401) as client, pytest.raises(HttpError) as raised:
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
    """Six Gulf countries fortnightly, rather than three weekly: the region is the one the
    dashboard cannot publish, and its postings do not churn fast enough to need weekly."""
    calls_per_run = len(load_roles()) * len(jsearch_countries())
    assert calls_per_run * JSEARCH_RUNS_PER_MONTH <= jsearch.MONTHLY_CALL_LIMIT * 0.8


# --- SmartRecruiters -------------------------------------------------------------------


def two_stage_client(listing: Any, detail: Any, requests: list[httpx.Request]) -> httpx.Client:
    """Answers the list endpoint with `listing` and any posting URL with `detail`."""

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        is_detail = not request.url.path.endswith("/postings")
        return httpx.Response(200, json=detail if is_detail else listing)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_smartrecruiters_only_fetches_details_worth_having(
    load_fixture: Callable[[str], Any],
) -> None:
    """The list carries the title and country, so out-of-scope postings cost no request."""
    requests: list[httpx.Request] = []
    listing = load_fixture("smartrecruiters_postings.json")
    with two_stage_client(listing, load_fixture("smartrecruiters_detail.json"), requests) as client:
        postings = smartrecruiters.fetch_postings(client, "BoschGroup")

    details = [r for r in requests if not r.url.path.endswith("/postings")]
    assert len(details) == 2, "two US postings have a relevant title; the other three do not"
    assert len(postings) == 2
    titles = [item["name"] for item in listing["content"]]
    assert "Azure Data Engineer" in titles, "a relevant title outside the curated regions"
    assert not any("Azure Data Engineer" in str(request.url) for request in details)


def test_smartrecruiters_parse_reads_detail(load_fixture: Callable[[str], Any]) -> None:
    posting = smartrecruiters.parse_posting(
        load_fixture("smartrecruiters_detail.json"), "Bosch Group"
    )
    assert posting.source == "smartrecruiters"
    assert posting.country == "US"
    assert posting.company == "Bosch Group"
    assert posting.url.startswith("https://jobs.smartrecruiters.com/")
    assert posting.description_text and "<p>" not in posting.description_text


def test_smartrecruiters_leaves_out_the_about_us_blurb(
    load_fixture: Callable[[str], Any],
) -> None:
    """Company boilerplate names no skills, so it is not part of the text we extract from."""
    detail = load_fixture("smartrecruiters_detail.json")
    detail["jobAd"]["sections"]["companyDescription"] = {"text": "<p>UNIQUE-BLURB-MARKER</p>"}

    posting = smartrecruiters.parse_posting(detail, "Bosch Group")

    assert "UNIQUE-BLURB-MARKER" not in posting.description_text


def test_smartrecruiters_pages_until_everything_is_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        page = [
            {"id": str(offset + n), "name": "Sales Manager", "location": {"country": "us"}}
            for n in range(smartrecruiters.PAGE_SIZE)
        ]
        return httpx.Response(200, json={"totalFound": 250, "content": page[: 250 - offset]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert smartrecruiters.fetch_postings(client, "big") == []  # none are in scope


# --- Workday ---------------------------------------------------------------------------


def workday_client(
    facets: Any, jobs: Any, detail: Any, requests: list[httpx.Request]
) -> httpx.Client:
    """Answers the facet probe, the paged listing, and any job detail separately."""

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=detail)
        body = json.loads(request.content)
        if not body.get("appliedFacets"):
            return httpx.Response(200, json=facets)
        return httpx.Response(200, json=jobs)

    return httpx.Client(transport=httpx.MockTransport(handler))


BOARD = "nvidia/wd5/NVIDIAExternalCareerSite"


def test_workday_board_url_needs_all_three_parts() -> None:
    assert workday.board_url(BOARD).endswith("/wday/cxs/nvidia/NVIDIAExternalCareerSite")
    for bad in ["nvidia", "nvidia/wd5", "nvidia//site", ""]:
        with pytest.raises(ValueError):
            workday.board_url(bad)


def test_workday_asks_only_for_curated_countries(load_fixture: Callable[[str], Any]) -> None:
    """The board offers China and India too; paying to list them would be waste."""
    requests: list[httpx.Request] = []
    with workday_client(
        load_fixture("workday_facets.json"),
        load_fixture("workday_jobs.json"),
        load_fixture("workday_detail.json"),
        requests,
    ) as client:
        workday.fetch_postings(client, BOARD)

    listing = json.loads(requests[1].content)
    applied = listing["appliedFacets"][workday.COUNTRY_FACETS[0]]
    facets = load_fixture("workday_facets.json")
    offered = {
        value["descriptor"]: value["id"]
        for facet in facets["facets"]
        for group in facet.get("values") or []
        if group.get("facetParameter") == workday.COUNTRY_FACETS[0]
        for value in group.get("values") or []
    }
    assert offered["United States"] in applied
    assert offered["United Kingdom"] in applied
    assert offered["China"] not in applied
    assert offered["India"] not in applied


def test_workday_fetches_details_only_for_relevant_titles(
    load_fixture: Callable[[str], Any],
) -> None:
    requests: list[httpx.Request] = []
    jobs = load_fixture("workday_jobs.json")
    with workday_client(
        load_fixture("workday_facets.json"), jobs, load_fixture("workday_detail.json"), requests
    ) as client:
        postings = workday.fetch_postings(client, BOARD)

    relevant = [job for job in jobs["jobPostings"] if is_relevant_title(job["title"])]
    details = [request for request in requests if request.method == "GET"]
    assert len(details) == len(relevant) < len(jobs["jobPostings"])
    assert len(postings) == len(relevant)


def test_workday_pages_past_the_first_response(load_fixture: Callable[[str], Any]) -> None:
    """Workday reports `total` only on page one; later pages say 0. Believing it every time
    ended the run after two pages and lost most of a board."""
    facets = load_fixture("workday_facets.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=load_fixture("workday_detail.json"))
        body = json.loads(request.content)
        if not body.get("appliedFacets"):
            return httpx.Response(200, json=facets)
        offset = body["offset"]
        page = [
            {"title": "Sales Manager", "externalPath": f"/job/{offset + n}"}
            for n in range(workday.PAGE_SIZE)
            if offset + n < 45
        ]
        return httpx.Response(200, json={"total": 45 if offset == 0 else 0, "jobPostings": page})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        listed, kept = workday.survey(client, BOARD)
    assert listed == 45, "all three pages should be read, not just the first two"
    assert kept == 0


def test_workday_parse_prefers_the_stated_country(load_fixture: Callable[[str], Any]) -> None:
    detail = load_fixture("workday_detail.json")["jobPostingInfo"]
    posting = workday.parse_posting(detail, "NVIDIA")
    assert posting.source == "workday"
    assert posting.country == "US"
    assert posting.description_text and "<p>" not in posting.description_text
    assert posting.url.startswith("https://")


def test_workday_reads_the_country_when_the_location_is_only_remote() -> None:
    """ "Remote" names no place, but Workday states the country separately."""
    posting = workday.parse_posting(
        {
            "id": "abc",
            "title": "Data Engineer",
            "externalUrl": "https://example.com/job/1",
            "location": "Remote",
            "country": {"descriptor": "United Kingdom"},
            "jobDescription": "<p>Build pipelines.</p>",
            "startDate": "2026-09-01",
        },
        "Acme",
    )
    assert posting.country == "GB"


def test_workday_lists_everything_when_the_board_has_no_country_facet() -> None:
    """Employers configure their own facets. Narrowing is an economy, not a requirement:
    without it the board is still read, and each posting states its own country."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "total": 10,
                "jobPostings": [],
                "facets": [
                    {
                        "facetParameter": "locationMainGroup",
                        "values": [
                            {
                                "facetParameter": workday.COUNTRY_FACETS[0],
                                "values": [{"descriptor": "India", "id": "x"}],
                            }
                        ],
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert workday.fetch_postings(client, BOARD) == []
    listing = json.loads(requests[1].content)
    assert listing["appliedFacets"] == {}, "no usable facet, so nothing is narrowed away"

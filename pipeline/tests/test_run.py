"""Ingestion units end to end: recorded responses in, rows in the test database out."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import psycopg

from pipeline.ingest import greenhouse, run
from pipeline.taxonomy import Company, get_country, get_role


def serving(payload: Any, requests: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_in_scope_keeps_curated_roles_in_curated_regions(
    load_fixture: Callable[[str], Any],
) -> None:
    postings = [
        greenhouse.parse_job(job, "Stripe") for job in load_fixture("greenhouse_jobs.json")["jobs"]
    ]
    # Dropped: Canada and Singapore (regions), an Account Executive (excluded), an investigator.
    assert [posting.title for posting in postings if run.in_scope(posting)] == ["Data Analyst, NYC"]


def test_parse_items_skips_malformed_items() -> None:
    postings, invalid = run.parse_items(
        [{"id": 1}], lambda item: greenhouse.parse_job(item, "Acme")
    )
    assert (postings, invalid) == ([], 1)


def test_ingest_board_stores_in_scope_postings_once(
    db: psycopg.Connection, load_fixture: Callable[[str], Any]
) -> None:
    company = Company(name="OpenAI", ats="ashby", board="openai")
    with serving(load_fixture("ashby_jobs.json")) as client:
        first = run.ingest_board(company, client=client, conn=db)
        second = run.ingest_board(company, client=client, conn=db)
    assert (first.fetched, first.invalid, first.kept, first.inserted) == (4, 0, 3, 3)
    assert (second.inserted, second.updated) == (0, 0)


def test_ingest_adzuna_stops_paging_when_a_page_comes_back_short(
    db: psycopg.Connection, load_fixture: Callable[[str], Any]
) -> None:
    requests: list[httpx.Request] = []
    with serving(load_fixture("adzuna_search_gb.json"), requests) as client:
        result = run.ingest_adzuna(
            get_country("GB").adzuna,
            get_role("data-engineer"),
            client=client,
            conn=db,
            app_id="id",
            app_key="key",
            pause_seconds=0,
        )
    assert len(requests) == 1  # 5 results is less than a full page of 50
    assert (result.fetched, result.kept, result.inserted) == (5, 5, 5)


def test_ingest_jsearch_drops_out_of_scope_titles(
    db: psycopg.Connection, load_fixture: Callable[[str], Any]
) -> None:
    with serving(load_fixture("jsearch_search_ae.json")) as client:
        result = run.ingest_jsearch(
            get_country("AE"), get_role("data-engineer"), client=client, conn=db, api_key="key"
        )
    assert (result.fetched, result.kept, result.inserted) == (4, 3, 3)  # "Head of ..." dropped

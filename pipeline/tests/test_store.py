"""Storage against a real Postgres: idempotent upserts and duplicate linking."""

from __future__ import annotations

from typing import Any

import psycopg

from pipeline.ingest.posting import FULL_TEXT_MIN_CHARS, RawPosting
from pipeline.ingest.store import link_duplicates, upsert_postings


def make(**overrides: Any) -> RawPosting:
    fields = {
        "source": "greenhouse",
        "source_id": "1",
        "url": "https://example.com/jobs/1",
        "title": "Data Engineer",
        "company": "Acme",
        "country": "GB",
        "description_text": "x" * FULL_TEXT_MIN_CHARS,
    }
    return RawPosting(**(fields | overrides))


def scalar(db: psycopg.Connection, sql: str) -> Any:
    return db.execute(sql).fetchone()[0]


def test_upsert_inserts_then_leaves_unchanged_postings_alone(db: psycopg.Connection) -> None:
    postings = [make(source_id="1"), make(source_id="2", title="Data Scientist")]
    first = upsert_postings(db, postings)
    second = upsert_postings(db, postings)
    assert (first.inserted, first.updated) == (2, 0)
    assert (second.inserted, second.updated) == (0, 0)
    assert scalar(db, "select count(*) from raw.postings") == 2


def test_upsert_updates_changed_content(db: psycopg.Connection) -> None:
    upsert_postings(db, [make()])
    result = upsert_postings(db, [make(description_text="y" * FULL_TEXT_MIN_CHARS)])
    assert (result.inserted, result.updated) == (0, 1)
    assert scalar(db, "select left(description_text, 1) from raw.postings") == "y"


def test_upsert_of_nothing_is_a_no_op(db: psycopg.Connection) -> None:
    assert upsert_postings(db, []) == upsert_postings(db, [])
    assert scalar(db, "select count(*) from raw.postings") == 0


def test_upsert_stores_derived_fields(db: psycopg.Connection) -> None:
    upsert_postings(db, [make(country="DE", description_text="short")])
    assert db.execute("select region, text_quality, role_hint from raw.postings").fetchone() == (
        "eu",
        "excerpt",
        "data-engineer",
    )


def test_aggregator_copy_links_to_the_job_board_posting(db: psycopg.Connection) -> None:
    upsert_postings(db, [make(source="adzuna", source_id="a1", company="Acme Ltd"), make()])
    assert link_duplicates(db) == 1
    board_id = scalar(db, "select id from raw.postings where source = 'greenhouse'")
    assert scalar(db, "select duplicate_of from raw.postings where source = 'greenhouse'") is None
    assert scalar(db, "select duplicate_of from raw.postings where source = 'adzuna'") == board_id


def test_same_title_twice_on_a_job_board_counts_twice(db: psycopg.Connection) -> None:
    upsert_postings(db, [make(source_id="1"), make(source_id="2")])
    assert link_duplicates(db) == 0
    assert scalar(db, "select count(*) from raw.postings where duplicate_of is null") == 2


def test_aggregator_reposts_of_one_job_collapse(db: psycopg.Connection) -> None:
    upsert_postings(
        db, [make(source="jsearch", source_id="j1"), make(source="jsearch", source_id="j2")]
    )
    link_duplicates(db)
    assert scalar(db, "select count(*) from raw.postings where duplicate_of is null") == 1


def test_full_text_copy_is_preferred_over_an_excerpt(db: psycopg.Connection) -> None:
    upsert_postings(
        db,
        [
            make(source="jsearch", source_id="snippet", description_text="short"),
            make(source="jsearch", source_id="complete"),
        ],
    )
    link_duplicates(db)
    assert scalar(db, "select source_id from raw.postings where duplicate_of is null") == "complete"


def test_link_duplicates_is_idempotent(db: psycopg.Connection) -> None:
    upsert_postings(db, [make(source="adzuna", source_id="a1"), make()])
    assert link_duplicates(db) == 1
    assert link_duplicates(db) == 0

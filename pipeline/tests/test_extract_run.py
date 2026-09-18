"""Extraction runs: what gets sent, what gets stored, and what is retried."""

from __future__ import annotations

import itertools
import json
import threading
import time
from typing import Any

import psycopg
import pytest

from pipeline.extract.llm.base import ModelAnswer, ModelError
from pipeline.extract.quota import DailyQuota, Pacer
from pipeline.extract.run import MAX_ATTEMPTS_PER_POSTING, extract_pending
from pipeline.http import HttpError
from pipeline.ingest.posting import FULL_TEXT_MIN_CHARS, RawPosting
from pipeline.ingest.store import upsert_postings

ANSWER = json.dumps(
    {
        "role": "data-engineer",
        "seniority": "senior",
        "years_experience_min": 5,
        "work_mode": "hybrid",
        "visa_sponsorship": "not_mentioned",
        "skills": [
            {"name": "Python", "kind": "language", "requirement": "required"},
            {"name": "dbt", "kind": "tool", "requirement": "preferred"},
        ],
    }
)

NO_PACE = Pacer(requests_per_minute=60_000, input_tokens_per_minute=10_000_000)


class FakeBackend:
    """Answers with the given replies in turn; an exception is raised instead of returned."""

    def __init__(self, *replies: str | Exception, name: str = "fake-model") -> None:
        self._replies = itertools.cycle(replies) if replies else itertools.repeat(ANSWER)
        self._lock = threading.Lock()
        self._name = name
        self.prompts: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def generate(self, prompt: str, schema: dict[str, Any]) -> ModelAnswer:
        with self._lock:
            self.prompts.append(prompt)
            reply = next(self._replies)
        if isinstance(reply, Exception):
            raise reply
        return ModelAnswer(text=reply, input_tokens=300, output_tokens=120)


def store_postings(db: psycopg.Connection, count: int, **overrides: Any) -> None:
    fields: dict[str, Any] = {
        "source": "greenhouse",
        "title": "Data Engineer",
        "company": "Acme",
        "country": "GB",
        "description_text": "Build pipelines. " * 80,
    }
    postings = [
        RawPosting(
            source_id=str(index),
            url=f"https://example.com/{index}",
            **(fields | overrides),
        )
        for index in range(count)
    ]
    upsert_postings(db, postings)
    db.commit()


def extractions(db: psycopg.Connection) -> list[tuple[Any, ...]]:
    return db.execute(
        "select status, payload, attempts, error, input_tokens, latency_ms from raw.extractions"
    ).fetchall()


def test_extracts_pending_postings_and_stores_the_payload(db: psycopg.Connection) -> None:
    store_postings(db, 2)
    backend = FakeBackend()

    result = extract_pending(db, backend, limit=10, pacer=NO_PACE, workers=1)

    assert (result.pending, result.granted, result.ok, result.invalid, result.failed) == (
        2,
        2,
        2,
        0,
        0,
    )
    assert result.rate_limited == 0
    rows = extractions(db)
    assert {row[0] for row in rows} == {"ok"}
    assert rows[0][1]["skills"][0]["name"] == "Python"
    assert rows[0][4] == 300 and rows[0][5] is not None
    assert "Build pipelines." in backend.prompts[0]


def test_postings_already_extracted_are_not_sent_again(db: psycopg.Connection) -> None:
    store_postings(db, 2)
    backend = FakeBackend()
    extract_pending(db, backend, limit=10, pacer=NO_PACE, workers=1)

    second = extract_pending(db, backend, limit=10, pacer=NO_PACE, workers=1)

    assert (second.pending, second.granted) == (0, 0)
    assert len(backend.prompts) == 2


def test_duplicate_postings_are_never_extracted(db: psycopg.Connection) -> None:
    store_postings(db, 1)
    db.execute(
        "insert into raw.postings (source, source_id, url, title, company, country, region,"
        " description_text, text_quality, content_hash, dedupe_key, duplicate_of)"
        " select 'adzuna', 'a1', url, title, company, country, region, description_text,"
        " 'excerpt', 'hash-copy', dedupe_key, id from raw.postings limit 1"
    )
    db.commit()

    result = extract_pending(db, FakeBackend(), limit=10, pacer=NO_PACE, workers=1)

    assert result.pending == 1


@pytest.mark.parametrize(
    ("reply", "status"),
    [
        ("not json at all", "invalid_json"),
        (json.dumps({"role": "data-engineer"}), "invalid_json"),  # missing required fields
        (ModelError("fake-model: empty answer"), "error"),
        (HttpError("Gemini fake-model: HTTP 503"), "error"),
    ],
)
def test_bad_answers_are_recorded_not_raised(
    db: psycopg.Connection, reply: str | Exception, status: str
) -> None:
    store_postings(db, 1)

    result = extract_pending(db, FakeBackend(reply), limit=10, pacer=NO_PACE, workers=1)

    assert (result.ok, result.invalid + result.failed) == (0, 1)
    stored = extractions(db)[0]
    assert stored[0] == status and stored[1] is None and stored[3]


def test_a_failing_posting_is_retried_then_given_up_on(db: psycopg.Connection) -> None:
    store_postings(db, 1)
    backend = FakeBackend(ModelError("fake-model: empty answer"))

    for attempt in range(1, MAX_ATTEMPTS_PER_POSTING + 2):
        result = extract_pending(db, backend, limit=10, pacer=NO_PACE, workers=1)
        if attempt <= MAX_ATTEMPTS_PER_POSTING:
            assert result.granted == 1, f"attempt {attempt} should still be tried"
        else:
            assert result.granted == 0, "should be given up on after the attempt limit"
    assert extractions(db)[0][2] == MAX_ATTEMPTS_PER_POSTING


def test_a_rate_limited_posting_is_left_pending_and_unmarked(db: psycopg.Connection) -> None:
    """A 429 is a fact about the minute, not the posting: it must not spend an attempt."""
    store_postings(db, 1)
    backend = FakeBackend(HttpError("Gemini: HTTP 429", status=429, retry_after=0.01))

    result = extract_pending(db, backend, limit=10, pacer=NO_PACE, workers=1)

    assert (result.rate_limited, result.failed, result.ok) == (1, 0, 0)
    assert extractions(db) == [], "nothing stored, so the next run picks it up unpenalised"

    second = extract_pending(db, FakeBackend(), limit=10, pacer=NO_PACE, workers=1)
    assert (second.granted, second.ok) == (1, 1)


def test_a_rate_limit_holds_the_other_workers_back(db: psycopg.Connection) -> None:
    store_postings(db, 1)
    pacer = Pacer(window_seconds=0.1)
    backend = FakeBackend(HttpError("Gemini: HTTP 429", status=429, retry_after=0.2))

    extract_pending(db, backend, limit=10, pacer=pacer, workers=1)

    started = time.monotonic()
    pacer.wait(1)
    assert time.monotonic() - started >= 0.1, "the pause outlives the request that caused it"


def test_rate_limited_requests_are_given_back_to_the_daily_budget(db: psycopg.Connection) -> None:
    store_postings(db, 2)
    backend = FakeBackend(HttpError("Gemini: HTTP 429", status=429, retry_after=0.01))
    quota = DailyQuota("fake-model", cap=10)

    extract_pending(db, backend, limit=10, quota=quota, pacer=NO_PACE, workers=1)

    row = db.execute(
        "select requests from raw.quota_usage where day = current_date and model = 'fake-model'"
    ).fetchone()
    assert row[0] == 0, "requests the provider refused did not spend the day's budget"


def test_the_daily_quota_caps_a_run(db: psycopg.Connection) -> None:
    store_postings(db, 5)
    backend = FakeBackend()

    result = extract_pending(
        db, backend, limit=10, quota=DailyQuota("fake-model", cap=3), pacer=NO_PACE, workers=1
    )

    assert (result.pending, result.granted, result.ok) == (5, 3, 3)
    assert len(extractions(db)) == 3


def test_workers_run_in_parallel(db: psycopg.Connection) -> None:
    store_postings(db, 6)
    backend = FakeBackend()

    result = extract_pending(db, backend, limit=10, pacer=NO_PACE, workers=3)

    assert (result.ok, len(backend.prompts)) == (6, 6)


def test_excerpt_postings_are_not_sent_to_the_model(db: psycopg.Connection) -> None:
    """A 500-character excerpt is company blurb: extracting it would spend quota for nothing."""
    store_postings(db, 1, description_text="About us: we are a fast-growing scale-up.")
    backend = FakeBackend()

    result = extract_pending(db, backend, limit=10, pacer=NO_PACE, workers=1)

    assert (result.pending, result.granted) == (0, 0)
    assert backend.prompts == []
    assert len("About us: we are a fast-growing scale-up.") < FULL_TEXT_MIN_CHARS

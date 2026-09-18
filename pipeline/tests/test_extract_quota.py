"""The daily budget and the pacer that together keep extraction inside the free tier."""

from __future__ import annotations

import time

import psycopg

from pipeline.extract.quota import DailyQuota, Pacer, estimate_tokens


def used(db: psycopg.Connection, model: str) -> int:
    row = db.execute(
        "select requests from raw.quota_usage where day = current_date and model = %s", (model,)
    ).fetchone()
    return row[0] if row else 0


def test_reserve_grants_what_is_left_and_counts_it(db: psycopg.Connection) -> None:
    quota = DailyQuota("gemma-test", cap=10)
    assert quota.reserve(db, 4) == 4
    assert quota.reserve(db, 4) == 4
    assert quota.reserve(db, 4) == 2  # only two left under the cap
    assert quota.reserve(db, 1) == 0
    assert used(db, "gemma-test") == 10


def test_reserving_nothing_is_a_no_op(db: psycopg.Connection) -> None:
    assert DailyQuota("gemma-test", cap=10).reserve(db, 0) == 0
    assert used(db, "gemma-test") == 0


def test_models_have_separate_budgets(db: psycopg.Connection) -> None:
    DailyQuota("model-a", cap=5).reserve(db, 5)
    assert DailyQuota("model-b", cap=5).reserve(db, 5) == 5
    assert used(db, "model-a") == used(db, "model-b") == 5


def test_unused_reservations_are_given_back(db: psycopg.Connection) -> None:
    quota = DailyQuota("gemma-test", cap=10)
    quota.reserve(db, 10)
    quota.release(db, 6)
    assert used(db, "gemma-test") == 4
    assert quota.reserve(db, 6) == 6


def fast_pacer(**limits: int) -> Pacer:
    """A pacer whose minute is a tenth of a second, so the budget can be tested quickly."""
    return Pacer(window_seconds=0.1, **limits)


def test_pacer_lets_a_request_through_while_the_budget_lasts() -> None:
    pacer = fast_pacer(requests_per_minute=10, input_tokens_per_minute=1000)
    assert pacer.wait(400) < 0.05
    assert pacer.wait(400) < 0.05


def test_pacer_waits_when_the_token_budget_is_spent() -> None:
    """The limit that binds is tokens, not requests: two big calls fill a 1,000-token minute."""
    pacer = fast_pacer(requests_per_minute=10, input_tokens_per_minute=1000)
    pacer.wait(600)
    pacer.wait(300)

    started = time.monotonic()
    pacer.wait(600)

    assert time.monotonic() - started >= 0.05, "should have waited for the window to roll"


def test_pacer_waits_when_the_request_budget_is_spent() -> None:
    pacer = fast_pacer(requests_per_minute=2, input_tokens_per_minute=1_000_000)
    pacer.wait(1)
    pacer.wait(1)

    started = time.monotonic()
    pacer.wait(1)

    assert time.monotonic() - started >= 0.05


def test_pacer_admits_a_request_larger_than_the_whole_budget() -> None:
    """Otherwise one oversized posting would block the run for ever."""
    pacer = fast_pacer(requests_per_minute=10, input_tokens_per_minute=100)
    assert pacer.wait(5000) < 0.05


def test_pause_holds_every_caller_back() -> None:
    pacer = fast_pacer(requests_per_minute=10, input_tokens_per_minute=1000)
    pacer.pause(0.1)

    started = time.monotonic()
    pacer.wait(10)

    assert time.monotonic() - started >= 0.05


def test_estimated_tokens_stay_within_the_measured_range() -> None:
    """Real prompts ran 3.9 to 5.3 characters per token, so a 10,000-character prompt is
    between 1,887 and 2,564 tokens. The estimate has to land in that band to be useful."""
    assert 1887 <= estimate_tokens("x" * 10_000) <= 2564
    assert estimate_tokens("") == 0

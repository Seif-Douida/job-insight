"""Keeps extraction inside the Gemini free tier: a daily budget and a steady pace.

The daily counter lives in Postgres (`raw.quota_usage`), so a restart cannot spend the
budget twice. The pacer is per-process and holds every worker thread inside the rolling
per-minute limits, of which the input-token one is what actually binds.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass

import psycopg

log = logging.getLogger(__name__)

DEFAULT_REQUESTS_PER_MINUTE = 25
"""Free tier allows 30/min for Gemma 4; leave headroom."""

DEFAULT_INPUT_TOKENS_PER_MINUTE = 15_000
"""Free tier allows 16,000 input tokens per minute for Gemma 4, and this, not the request
count, is the limit that binds: one posting costs about 2,000 input tokens, so the tokens
run out at roughly 8 requests a minute. Measured 2026-09-17 from the API's own refusal
(quotaId `GenerateContentInputTokensPerModelPerMinute-FreeTier`, limit 16000).

The remaining 1,000 is headroom for a minute of unusually dense text. Going slightly over
is not a disaster: the provider says how long to wait and `Pacer.pause` waits exactly that
long, so the cost of an occasional overshoot is one short hold, not a failed posting."""

DEFAULT_DAILY_CAP = 13000
"""Free tier allows 14,400/day for Gemma 4."""

WINDOW_SECONDS = 60.0
CHARS_PER_TOKEN = 4.8
"""The median over 800 real prompts, whose range was 3.9 to 5.3 characters per token.

Deliberately the median rather than the densest: an estimate built on the densest prompt
proved 22% high on average, which would have left a fifth of the budget unused. Being
right on average and occasionally waiting out a 429 collects more than being always
pessimistic."""

MIN_SLEEP_SECONDS = 0.01


def estimate_tokens(text: str) -> int:
    """Roughly how many input tokens `text` will cost, rounded up."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


class Pacer:
    """Holds every worker inside the per-minute request and input-token limits.

    Requests are not spaced evenly: what the provider measures is the rolling minute, so
    that is what this tracks. A run of short postings is allowed to go faster, and a long
    one costs more of the budget.
    """

    def __init__(
        self,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        input_tokens_per_minute: int = DEFAULT_INPUT_TOKENS_PER_MINUTE,
        window_seconds: float = WINDOW_SECONDS,
    ) -> None:
        self._max_requests = requests_per_minute
        self._max_tokens = input_tokens_per_minute
        self._window = window_seconds
        self._lock = threading.Lock()
        self._spent: deque[tuple[float, int]] = deque()
        self._paused_until = 0.0

    def wait(self, tokens: int = 0) -> float:
        """Block until a request of this size fits; returns how long it waited."""
        started = time.monotonic()
        while True:
            with self._lock:
                delay = self._admit(tokens)
            if delay <= 0.0:
                return time.monotonic() - started
            time.sleep(max(delay, MIN_SLEEP_SECONDS))

    def pause(self, seconds: float) -> None:
        """Hold every worker back, after the server said we are over its limit."""
        with self._lock:
            self._paused_until = max(self._paused_until, time.monotonic() + seconds)

    def _admit(self, tokens: int) -> float:
        """Record the spend and return 0 if the request may go now, else seconds to wait."""
        now = time.monotonic()
        while self._spent and self._spent[0][0] <= now - self._window:
            self._spent.popleft()
        if now < self._paused_until:
            return self._paused_until - now
        if self._spent:
            spent_tokens = sum(spent for _, spent in self._spent)
            over_budget = (
                len(self._spent) >= self._max_requests or spent_tokens + tokens > self._max_tokens
            )
            if over_budget:
                # Wait for the oldest spend to leave the window; nothing frees up sooner.
                return self._spent[0][0] + self._window - now
        self._spent.append((now, tokens))
        return 0.0


@dataclass(frozen=True)
class DailyQuota:
    """The day's request budget for one model, counted in the database."""

    model: str
    cap: int = DEFAULT_DAILY_CAP

    def reserve(self, conn: psycopg.Connection, requested: int) -> int:
        """Claim up to `requested` requests for today; returns how many were granted."""
        if requested <= 0:
            return 0
        with conn.transaction():
            row = conn.execute(
                "select requests from raw.quota_usage where day = current_date and model = %s"
                " for update",
                (self.model,),
            ).fetchone()
            used = row[0] if row else 0
            granted = max(0, min(requested, self.cap - used))
            if granted:
                conn.execute(
                    """
                    insert into raw.quota_usage (day, model, requests)
                    values (current_date, %s, %s)
                    on conflict (day, model)
                      do update set requests = raw.quota_usage.requests + excluded.requests
                    """,
                    (self.model, granted),
                )
        if granted < requested:
            log.warning(
                "Daily quota for %s nearly spent: granted %d of %d requested (cap %d)",
                self.model,
                granted,
                requested,
                self.cap,
            )
        return granted

    def release(self, conn: psycopg.Connection, unused: int) -> None:
        """Give back requests that were reserved but never sent."""
        if unused > 0:
            conn.execute(
                "update raw.quota_usage set requests = greatest(0, requests - %s)"
                " where day = current_date and model = %s",
                (unused, self.model),
            )

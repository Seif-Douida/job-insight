"""Shared fixtures: recorded API responses, and a disposable Postgres for storage tests."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from functools import cache
from pathlib import Path
from typing import Any

import psycopg
import pytest

from pipeline.db.migrate import apply_schema

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture() -> Callable[[str], Any]:
    """Parse a recorded API response from tests/fixtures (a fresh copy on every call)."""

    def load(name: str) -> Any:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    return load


@cache
def _prepare(url: str) -> str | None:
    """Apply the schema, or return why these tests cannot run. Attempted once per session.

    A session-scoped fixture that skips does not cache the skip, so without this every test
    needing a database would open its own doomed connection and wait for it to time out —
    turning a stopped container into a four-minute run that ends in skips. The reason is
    worked out once and reused.
    """
    try:
        # Probed with a short timeout before doing any work. An absent database should be
        # reported in seconds, and it is not always refused promptly: Docker Desktop keeps a
        # proxy on localhost ports, so a port nothing is bound to can swallow the connection
        # and hang for minutes rather than answering.
        psycopg.connect(url, connect_timeout=5).close()
        apply_schema(url)
    except psycopg.OperationalError:
        # Configured but not running: the usual case being the local compose stack stopped,
        # which is a reasonable state for a laptop once the pipeline lives on a server.
        return (
            "TEST_DATABASE_URL is set but the database is unreachable. Start it with "
            "'docker compose -f infra/docker-compose.yml up -d postgres', or unset the "
            "variable to skip these tests deliberately."
        )
    return None


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; database tests skipped")
    if "neon.tech" in url:
        pytest.fail(
            "TEST_DATABASE_URL points at Neon. Tests truncate tables: use a local database."
        )
    reason = _prepare(url)
    if reason:
        pytest.skip(reason)
    return url


@pytest.fixture
def db(test_database_url: str) -> Iterator[psycopg.Connection]:
    """A connection to an emptied test database. Nothing is committed."""
    with psycopg.connect(test_database_url) as conn:
        conn.execute("truncate raw.extractions, raw.postings, raw.quota_usage restart identity")
        yield conn
        conn.rollback()

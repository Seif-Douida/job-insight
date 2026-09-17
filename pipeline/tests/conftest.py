"""Shared fixtures: recorded API responses, and a disposable Postgres for storage tests."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
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


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; database tests skipped")
    if "neon.tech" in url:
        pytest.fail(
            "TEST_DATABASE_URL points at Neon. Tests truncate tables: use a local database."
        )
    apply_schema(url)
    return url


@pytest.fixture
def db(test_database_url: str) -> Iterator[psycopg.Connection]:
    """A connection to an emptied test database. Nothing is committed."""
    with psycopg.connect(test_database_url) as conn:
        conn.execute("truncate raw.extractions, raw.postings, raw.quota_usage restart identity")
        yield conn
        conn.rollback()

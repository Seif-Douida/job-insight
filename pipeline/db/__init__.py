"""Database access. One connection helper, used by every task that touches Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from pipeline.config import database_url


@contextmanager
def connect(dsn: str | None = None) -> Iterator[psycopg.Connection]:
    """Open a connection to the project database, committing on clean exit."""
    with psycopg.connect(dsn or database_url()) as conn:
        yield conn

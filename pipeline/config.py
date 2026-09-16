"""Paths and environment configuration.

Values come from the repo-root `.env` (see infra/.env.example). Inside the Airflow
container the same variables arrive through the environment, so nothing changes.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "infra" / "sql"

load_dotenv(REPO_ROOT / ".env")


def require_env(name: str) -> str:
    """Return an environment variable, failing loudly when it is missing."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Copy infra/.env.example to .env and fill it in.")
    return value


def database_url() -> str:
    """Connection string for the Neon Postgres holding raw data and marts."""
    return require_env("DATABASE_URL")

"""Deriving dbt's connection settings from the one connection string in .env."""

from __future__ import annotations

import pytest
import yaml

from pipeline.db.dbt_profile import render

NEON_URL = (
    "postgresql://jobs_owner:npg_S3cr3t@ep-x.eu-west-2.aws.neon.tech/jobinsight?sslmode=require"
)


def profile(url: str) -> dict:
    return yaml.safe_load(render(url))["job_insight"]["outputs"]["prod"]


def test_reads_every_field_dbt_needs() -> None:
    output = profile(NEON_URL)
    assert output["host"] == "ep-x.eu-west-2.aws.neon.tech"
    assert output["user"] == "jobs_owner"
    assert output["password"] == "npg_S3cr3t"
    assert output["dbname"] == "jobinsight"
    assert output["port"] == 5432
    assert output["sslmode"] == "require"


def test_an_explicit_port_is_kept() -> None:
    assert profile("postgresql://u:p@localhost:5433/testdb")["port"] == 5433


def test_percent_encoded_credentials_are_decoded() -> None:
    """A password with a @ or / in it arrives encoded, and dbt wants it decoded."""
    assert profile("postgresql://u%40corp:p%2Fw%40rd@host/db")["user"] == "u@corp"
    assert profile("postgresql://u%40corp:p%2Fw%40rd@host/db")["password"] == "p/w@rd"


@pytest.mark.parametrize("url", ["", "postgresql:///db", "not-a-url"])
def test_an_unusable_url_fails_loudly(url: str) -> None:
    with pytest.raises(ValueError):
        render(url)

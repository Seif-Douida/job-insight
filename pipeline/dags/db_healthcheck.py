"""Smoke-test DAG: proves Airflow can import the pipeline package and reach the database.

Run it once after `docker compose up` to confirm the wiring before real DAGs arrive.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task


@dag(
    dag_id="db_healthcheck",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["ops"],
)
def db_healthcheck() -> None:
    @task
    def check_taxonomy() -> dict[str, int]:
        """The taxonomy YAML files load and are non-empty."""
        from pipeline.taxonomy import load_countries, load_roles

        counts = {"roles": len(load_roles()), "countries": len(load_countries())}
        if not all(counts.values()):
            raise ValueError(f"Empty taxonomy: {counts}")
        return counts

    @task
    def check_database() -> dict[str, int]:
        """The raw schema exists and is queryable."""
        from pipeline.db import connect

        with connect() as conn:
            postings = conn.execute("select count(*) from raw.postings").fetchone()
            extractions = conn.execute("select count(*) from raw.extractions").fetchone()
        return {"postings": postings[0], "extractions": extractions[0]}

    check_taxonomy()
    check_database()


db_healthcheck()

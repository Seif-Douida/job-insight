"""Rebuild the dbt models after the day's extraction.

Runs at 08:00, two hours after `extract` starts, so the marts describe postings that were
read out this morning rather than yesterday's. dbt is invoked as a command rather than
through an operator library: one call, nothing to configure, and the same command a person
runs locally.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task

PROJECT_DIR = "/opt/airflow/repo/pipeline/dbt"


@dag(
    dag_id="transform",
    schedule="0 8 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": pendulum.duration(minutes=10)},
    tags=["transform"],
)
def transform() -> None:
    @task
    def write_dbt_profile() -> str:
        """Derive profiles.yml from DATABASE_URL, so the container needs no extra secret."""
        from pipeline.config import require_env
        from pipeline.db.dbt_profile import PROFILES_PATH, render

        PROFILES_PATH.write_text(render(require_env("DATABASE_URL")), encoding="utf-8")
        return str(PROFILES_PATH)

    @task(execution_timeout=pendulum.duration(minutes=30))
    def dbt_build() -> str:
        """`dbt build`: models first, then the data tests that guard every published number.

        A failing test fails the task, which is the point - a mart with an impossible
        percentage should stop the pipeline, not reach the dashboard.
        """
        import subprocess

        result = subprocess.run(
            [
                "dbt",
                "build",
                "--project-dir",
                PROJECT_DIR,
                "--profiles-dir",
                PROJECT_DIR,
                # The repo is mounted, so `target/` may hold a parse cache written by the
                # dbt on the host, under a different Python. Reusing it fails deep inside
                # the parser (KeyError on a dbt_postgres macro), so this run parses afresh.
                "--no-partial-parse",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        tail = "\n".join(result.stdout.strip().splitlines()[-25:])
        if result.returncode != 0:
            raise RuntimeError(f"dbt build failed:\n{tail}")
        return tail

    write_dbt_profile() >> dbt_build()


transform()

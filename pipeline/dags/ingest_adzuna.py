"""Weekly Adzuna ingestion: every curated role in every Adzuna market.

Queries run one at a time with a pause after each call, keeping under Adzuna's
per-minute limit. The monthly call budget is enforced by a unit test on the config.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, get_current_context, task


@dag(
    dag_id="ingest_adzuna",
    schedule="0 4 * * 1",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    max_active_tasks=1,
    default_args={"retries": 1, "retry_delay": pendulum.duration(minutes=10)},
    tags=["ingest"],
)
def ingest_adzuna() -> None:
    @task
    def list_queries() -> list[dict[str, str]]:
        from pipeline.taxonomy import adzuna_markets, load_roles

        return [
            {"country": market.country, "role": role.slug}
            for market in adzuna_markets()
            for role in load_roles()
        ]

    @task(map_index_template="{{ query_label }}")
    def ingest_query(query: dict[str, str]) -> dict[str, str | int]:
        from pipeline.config import require_env
        from pipeline.db import connect
        from pipeline.ingest.http import make_client
        from pipeline.ingest.run import ingest_adzuna as run_query
        from pipeline.taxonomy import get_country, get_role

        market, role = get_country(query["country"]).adzuna, get_role(query["role"])
        get_current_context()["query_label"] = f"{market.market}:{role.slug}"
        with make_client() as client, connect() as conn:
            result = run_query(
                market,
                role,
                client=client,
                conn=conn,
                app_id=require_env("ADZUNA_APP_ID"),
                app_key=require_env("ADZUNA_APP_KEY"),
            )
        return result.as_dict()

    @task(trigger_rule="all_done")
    def link_duplicates() -> int:
        from pipeline.db import connect
        from pipeline.ingest.store import link_duplicates as link

        with connect() as conn:
            return link(conn)

    @task(trigger_rule="one_failed", retries=0)
    def fail_run_if_a_query_failed() -> None:
        """link_duplicates runs whatever happens, so on its own it would mark the run green."""
        raise RuntimeError("At least one Adzuna query failed; see its task log.")

    results = ingest_query.expand(query=list_queries())
    results >> link_duplicates()
    results >> fail_run_if_a_query_failed()


ingest_adzuna()

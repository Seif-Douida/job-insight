"""Weekly JSearch ingestion: every curated role in each Gulf country flagged for JSearch.

One call per query; the monthly call budget is enforced by a unit test on the config.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, get_current_context, task


@dag(
    dag_id="ingest_jsearch",
    schedule="0 5 * * 1",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    max_active_tasks=1,
    default_args={"retries": 1, "retry_delay": pendulum.duration(minutes=10)},
    tags=["ingest"],
)
def ingest_jsearch() -> None:
    @task
    def list_queries() -> list[dict[str, str]]:
        from pipeline.taxonomy import jsearch_countries, load_roles

        return [
            {"country": country.code, "role": role.slug}
            for country in jsearch_countries()
            for role in load_roles()
        ]

    @task(map_index_template="{{ query_label }}")
    def ingest_query(query: dict[str, str]) -> dict[str, str | int]:
        from pipeline.config import require_env
        from pipeline.db import connect
        from pipeline.http import make_client
        from pipeline.ingest.run import ingest_jsearch as run_query
        from pipeline.taxonomy import get_country, get_role

        country, role = get_country(query["country"]), get_role(query["role"])
        get_current_context()["query_label"] = f"{country.code.lower()}:{role.slug}"
        with make_client() as client, connect() as conn:
            result = run_query(
                country, role, client=client, conn=conn, api_key=require_env("JSEARCH_API_KEY")
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
        raise RuntimeError("At least one JSearch query failed; see its task log.")

    results = ingest_query.expand(query=list_queries())
    results >> link_duplicates()
    results >> fail_run_if_a_query_failed()


ingest_jsearch()

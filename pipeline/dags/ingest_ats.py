"""Daily ingestion from company job boards (Greenhouse, Lever, Ashby).

One mapped task per company, so a broken board retries on its own without re-reading the
others. Duplicates are linked once every board has been read, even if some failed.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, get_current_context, task

from pipeline.alerts import notify_failure


@dag(
    dag_id="ingest_ats",
    schedule="0 3 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    max_active_tasks=4,
    default_args={"retries": 2, "retry_delay": pendulum.duration(minutes=5)},
    on_failure_callback=notify_failure,
    tags=["ingest"],
)
def ingest_ats() -> None:
    @task
    def list_companies() -> list[dict[str, str]]:
        from dataclasses import asdict

        from pipeline.taxonomy import load_companies

        return [asdict(company) for company in load_companies()]

    @task(map_index_template="{{ board_label }}")
    def ingest_company(company: dict[str, str]) -> dict[str, str | int]:
        from pipeline.db import connect
        from pipeline.http import make_client
        from pipeline.ingest.run import ingest_board
        from pipeline.taxonomy import Company

        board = Company(**company)
        get_current_context()["board_label"] = f"{board.ats}:{board.board}"
        with make_client() as client, connect() as conn:
            return ingest_board(board, client=client, conn=conn).as_dict()

    @task(trigger_rule="all_done")
    def link_duplicates() -> int:
        from pipeline.db import connect
        from pipeline.ingest.store import link_duplicates as link

        with connect() as conn:
            return link(conn)

    @task(trigger_rule="one_failed", retries=0)
    def fail_run_if_a_board_failed() -> None:
        """link_duplicates runs whatever happens, so on its own it would mark the run green."""
        raise RuntimeError("At least one company board failed; see its task log.")

    results = ingest_company.expand(company=list_companies())
    results >> link_duplicates()
    results >> fail_run_if_a_board_failed()


ingest_ats()

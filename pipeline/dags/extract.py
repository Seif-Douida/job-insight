"""Daily extraction: send postings with no extraction yet to the model, then trim text.

One task, not one per posting: the run is paced by the rate limiter, so splitting it
would not make it faster and would only spread the quota counter across tasks.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task


@dag(
    dag_id="extract",
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": pendulum.duration(minutes=15)},
    tags=["extract"],
)
def extract() -> None:
    @task(execution_timeout=pendulum.duration(hours=5))
    def extract_postings() -> dict[str, str | int]:
        from pipeline.config import env_int, require_env
        from pipeline.db import connect
        from pipeline.extract.llm import GeminiBackend
        from pipeline.extract.quota import DailyQuota, Pacer
        from pipeline.extract.run import extract_pending
        from pipeline.http import make_client

        model = require_env("EXTRACTION_MODEL")
        with make_client(timeout_seconds=180) as client, connect() as conn:
            backend = GeminiBackend(
                api_key=require_env("GEMINI_API_KEY"), model=model, client=client
            )
            result = extract_pending(
                conn,
                backend,
                limit=env_int("EXTRACTION_BATCH", 2000),
                quota=DailyQuota(model, cap=env_int("EXTRACTION_DAILY_CAP", 13000)),
                pacer=Pacer(
                    requests_per_minute=env_int("EXTRACTION_RPM", 25),
                    input_tokens_per_minute=env_int("EXTRACTION_TPM", 15000),
                ),
                workers=env_int("EXTRACTION_WORKERS", 5),
            )
        return result.as_dict()

    @task
    def archive_extracted_text() -> int:
        from pipeline.config import require_env
        from pipeline.db import connect
        from pipeline.extract.archive import archive_and_trim

        with connect() as conn:
            return archive_and_trim(conn, model=require_env("EXTRACTION_MODEL"), batch=2000)

    extract_postings() >> archive_extracted_text()


extract()

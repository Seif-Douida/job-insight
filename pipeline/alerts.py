"""Say something out loud when a scheduled run fails.

The pipeline runs unattended at three in the morning. Airflow records a failure perfectly
well, but a record nobody reads is not an alert, and the whole point of the watcher task on
every ingest DAG was to make a failure visible rather than let a cleanup step paint the run
green. This carries that the last step: off the server and onto a phone.

One environment variable, `ALERT_WEBHOOK_URL`, decides where. Discord, Slack and ntfy all
accept a plain JSON POST, so the payload carries the same text under both keys those
services look for and works with any of them unconfigured. When the variable is unset
nothing is sent and the failure is logged — which is the right behaviour for a laptop.

Nothing here may raise. A callback that throws while reporting a failure replaces a clear
error with a confusing one, and the webhook URL is a credential: it is never logged, never
put in a message, and never included in an exception.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import httpx

WEBHOOK_ENV = "ALERT_WEBHOOK_URL"
TIMEOUT_SECONDS = 10.0
MAX_NAMED_TASKS = 8
"""Beyond this, a message lists a count instead of every name. One broken board is worth
naming; forty is a wall of text that says less than "40 boards failed"."""

log = logging.getLogger(__name__)


@contextmanager
def _quiet_httpx() -> Iterator[None]:
    """Stop httpx logging the request line while a webhook URL is being used.

    httpx logs every request at INFO as `HTTP Request: POST <full url> "200 OK"`. For every
    other call in this project that is useful; here the URL *is* the credential, and Airflow
    captures task logs, so an alert would write a token that grants posting rights into a
    file. Being careful not to log a secret is not enough when a library logs it for you.

    The suppression is global for the length of one POST. Alerts are rare and brief, and the
    alternative — a URL that cannot be kept out of the logs at all — is worse.
    """
    httpx_log = logging.getLogger("httpx")
    previous = httpx_log.level
    httpx_log.setLevel(logging.WARNING)
    try:
        yield
    finally:
        httpx_log.setLevel(previous)


def send_alert(text: str, *, client: httpx.Client | None = None) -> bool:
    """Post `text` to the configured webhook. Returns whether it was delivered.

    Never raises: the caller is already handling a failure and a second one helps nobody.
    """
    url = os.environ.get(WEBHOOK_ENV)
    if not url:
        log.warning("no %s configured, alert not sent: %s", WEBHOOK_ENV, text)
        return False

    # `content` is what Discord reads, `text` is what Slack and ntfy read. Sending both
    # means the same webhook setting works for any of them with nothing to choose.
    payload = {"content": text, "text": text}

    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        with _quiet_httpx():
            response = client.post(url, json=payload)
        if response.status_code >= 400:
            # The status, never the URL: it is a credential that grants posting rights.
            log.error("alert webhook rejected the message (HTTP %s)", response.status_code)
            return False
        return True
    except Exception as exc:
        log.error("alert webhook unreachable: %s", type(exc).__name__)
        return False
    finally:
        if owned:
            client.close()


def failed_task_ids(context: Mapping[str, Any]) -> list[str]:
    """Which tasks failed, when Airflow will tell us cheaply. Empty when it will not."""
    dag_run = context.get("dag_run")
    if dag_run is None:
        return []
    try:
        instances = dag_run.get_task_instances(state="failed")
        return sorted(
            f"{ti.task_id}[{ti.map_index}]" if getattr(ti, "map_index", -1) >= 0 else ti.task_id
            for ti in instances
        )
    except Exception:
        # Reaching the metadata database from inside a callback is a convenience, not a
        # requirement. Without it the alert still names the DAG, which is the useful part.
        return []


def failure_message(context: Mapping[str, Any]) -> str:
    """A line someone can act on, read on a phone, without opening anything."""
    dag = context.get("dag")
    dag_id = getattr(dag, "dag_id", None) or context.get("dag_id") or "unknown DAG"

    dag_run = context.get("dag_run")
    run_id = getattr(dag_run, "run_id", None) or context.get("run_id") or "unknown run"

    message = f"job-insight: {dag_id} failed ({run_id})"

    failed = failed_task_ids(context)
    if len(failed) > MAX_NAMED_TASKS:
        message += f" — {len(failed)} tasks failed"
    elif failed:
        message += " — " + ", ".join(failed)

    return message


def notify_failure(context: Mapping[str, Any]) -> None:
    """Airflow `on_failure_callback`. Attached to the DAG, so one run sends one alert.

    Attaching it per task would send one message per failed task, and the ingest DAGs map
    a task over 185 company boards.
    """
    try:
        send_alert(failure_message(context))
    except Exception as exc:
        log.error("failure alert could not be built: %s", type(exc).__name__)

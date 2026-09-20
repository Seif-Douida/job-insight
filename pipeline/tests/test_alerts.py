"""Alerting is the last link in the chain, and it runs only when something is already wrong.

So the cases worth pinning down are the awkward ones: no webhook configured, a webhook that
rejects the message, a webhook that cannot be reached, and a context that is missing the
things the message wants to say. None of them may raise, because every one of them happens
while Airflow is reporting a real failure that must not be replaced by this one.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pipeline.alerts import (
    WEBHOOK_ENV,
    failure_message,
    notify_failure,
    send_alert,
)

WEBHOOK = "https://example.invalid/hooks/secret-token"


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(WEBHOOK_ENV, WEBHOOK)


def client_recording(sink: list[httpx.Request], status: int = 204) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        sink.append(request)
        return httpx.Response(status)

    return httpx.Client(transport=httpx.MockTransport(handler))


class FakeTaskInstance:
    def __init__(self, task_id: str, map_index: int = -1) -> None:
        self.task_id = task_id
        self.map_index = map_index


class FakeDagRun:
    def __init__(self, run_id: str, failed: list[FakeTaskInstance] | None = None) -> None:
        self.run_id = run_id
        self._failed = failed or []

    def get_task_instances(self, state: str) -> list[FakeTaskInstance]:
        assert state == "failed"
        return self._failed


class FakeDag:
    def __init__(self, dag_id: str) -> None:
        self.dag_id = dag_id


def context(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "dag": FakeDag("ingest_ats"),
        "dag_run": FakeDagRun("scheduled__2026-09-20T03:00:00+00:00"),
    }
    base.update(overrides)
    return base


# --- sending ----------------------------------------------------------------------------


def test_sends_the_text_under_both_keys(configured: None) -> None:
    """One webhook setting has to work for Discord or Slack without being told which."""
    sent: list[httpx.Request] = []
    import json

    assert send_alert("something broke", client=client_recording(sent)) is True

    body = json.loads(sent[0].content)
    assert body == {"content": "something broke", "text": "something broke"}
    assert str(sent[0].url) == WEBHOOK


def test_without_a_webhook_nothing_is_sent_and_nothing_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(WEBHOOK_ENV, raising=False)
    sent: list[httpx.Request] = []

    assert send_alert("something broke", client=client_recording(sent)) is False
    assert sent == []


def test_a_rejected_message_is_reported_not_raised(configured: None) -> None:
    sent: list[httpx.Request] = []
    assert send_alert("something broke", client=client_recording(sent, status=403)) is False


def test_an_unreachable_webhook_is_reported_not_raised(configured: None) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    client = httpx.Client(transport=httpx.MockTransport(explode))
    assert send_alert("something broke", client=client) is False


def test_the_webhook_url_never_reaches_the_logs(
    configured: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The URL is a credential: anyone holding it can post as us."""
    sent: list[httpx.Request] = []
    with caplog.at_level("DEBUG"):
        send_alert("something broke", client=client_recording(sent, status=500))

    assert "secret-token" not in caplog.text
    assert WEBHOOK not in caplog.text


# --- the message ------------------------------------------------------------------------


def test_message_names_the_dag_and_the_run() -> None:
    message = failure_message(context())
    assert "ingest_ats" in message
    assert "scheduled__2026-09-20T03:00:00+00:00" in message


def test_message_names_the_tasks_that_failed() -> None:
    run = FakeDagRun("run-1", [FakeTaskInstance("ingest_company", 4), FakeTaskInstance("link")])
    message = failure_message(context(dag_run=run))
    assert "ingest_company[4]" in message
    assert "link" in message


def test_many_failures_are_counted_rather_than_listed() -> None:
    """185 boards can fail at once; a wall of names says less than the number."""
    run = FakeDagRun("run-1", [FakeTaskInstance("ingest_company", i) for i in range(40)])
    message = failure_message(context(dag_run=run))
    assert "40 tasks failed" in message
    assert "ingest_company[0]" not in message


def test_a_context_missing_everything_still_produces_a_message() -> None:
    assert failure_message({}) == "job-insight: unknown DAG failed (unknown run)"


def test_a_database_that_will_not_answer_does_not_stop_the_alert() -> None:
    class Unreachable(FakeDagRun):
        def get_task_instances(self, state: str) -> list[FakeTaskInstance]:
            raise RuntimeError("no session available in this context")

    message = failure_message(context(dag_run=Unreachable("run-1")))
    assert "run-1" in message


def test_notify_failure_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Airflow calls this while handling a failure; it must not introduce a second one."""
    monkeypatch.setenv(WEBHOOK_ENV, WEBHOOK)

    class Hostile:
        @property
        def dag_id(self) -> str:
            raise RuntimeError("nothing about this context is safe to touch")

    notify_failure({"dag": Hostile()})

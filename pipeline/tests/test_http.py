"""get_json: transient failures are retried, permanent ones fail fast, credentials never leak."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from pipeline.http import HttpError, get_json

NO_WAIT = (0.0, 0.0)
URL = "https://api.example.com/jobs?app_key=my-secret"


def client_answering(*answers: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    """A client whose n-th request is handled by the n-th answer."""
    remaining = list(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        return remaining.pop(0)(request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def reset(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadError("connection reset by peer", request=request)


def status(code: int) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(code)


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"jobs": []})


def test_connection_reset_is_retried() -> None:
    with client_answering(reset, ok) as client:
        assert get_json(client, URL, label="test", retry_delays=NO_WAIT) == {"jobs": []}


def test_server_errors_and_rate_limits_are_retried() -> None:
    with client_answering(status(503), status(429), ok) as client:
        assert get_json(client, URL, label="test", retry_delays=NO_WAIT) == {"jobs": []}


def test_gives_up_after_the_last_retry() -> None:
    with client_answering(reset, reset, reset) as client, pytest.raises(HttpError) as raised:
        get_json(client, URL, label="Adzuna gb", retry_delays=NO_WAIT)
    assert str(raised.value) == "Adzuna gb: ReadError"


def test_a_caller_can_exclude_a_status_from_the_retries() -> None:
    """The model backend handles its own rate limits: retrying here would bypass the pacer."""
    with client_answering(status(429)) as client, pytest.raises(HttpError) as raised:
        get_json(client, URL, label="Gemini", retry_delays=NO_WAIT, retry_statuses={500})
    assert raised.value.status == 429


def test_the_servers_own_retry_delay_is_read() -> None:
    """Gemini puts it in the body rather than in a Retry-After header."""
    body = {
        "error": {
            "code": 429,
            "message": "Quota exceeded",
            "details": [
                {"@type": "type.googleapis.com/google.rpc.Help", "links": []},
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "22s"},
            ],
        }
    }

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json=body)

    with client_answering(answer) as client, pytest.raises(HttpError) as raised:
        get_json(client, URL, label="Gemini", retry_delays=NO_WAIT, retry_statuses=set())
    assert raised.value.retry_after == 22.0


def test_a_retry_after_header_is_read() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "7"})

    with client_answering(answer) as client, pytest.raises(HttpError) as raised:
        get_json(client, URL, label="Gemini", retry_delays=NO_WAIT, retry_statuses=set())
    assert raised.value.retry_after == 7.0


def test_a_failure_without_a_stated_delay_says_so() -> None:
    with client_answering(status(429)) as client, pytest.raises(HttpError) as raised:
        get_json(client, URL, label="Gemini", retry_delays=NO_WAIT, retry_statuses=set())
    assert raised.value.retry_after is None


def test_client_errors_are_not_retried() -> None:
    with client_answering(status(404)) as client, pytest.raises(HttpError) as raised:
        get_json(client, URL, label="Lever acme", retry_delays=NO_WAIT)
    assert str(raised.value) == "Lever acme: HTTP 404"


def maintenance_page(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<html>maintenance</html>")


def test_invalid_json_is_a_source_error() -> None:
    with (
        client_answering(maintenance_page) as client,
        pytest.raises(HttpError, match="not valid JSON"),
    ):
        get_json(client, URL, label="test", retry_delays=NO_WAIT)


def test_errors_never_include_the_url() -> None:
    with client_answering(reset, reset, reset) as client, pytest.raises(HttpError) as raised:
        get_json(client, URL, label="test", retry_delays=NO_WAIT)
    assert "my-secret" not in str(raised.value)
    assert raised.value.__suppress_context__

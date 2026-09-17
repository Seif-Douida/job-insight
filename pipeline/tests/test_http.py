"""get_json: transient failures are retried, permanent ones fail fast, credentials never leak."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from pipeline.ingest.http import SourceError, get_json

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
    with client_answering(reset, reset, reset) as client, pytest.raises(SourceError) as raised:
        get_json(client, URL, label="Adzuna gb", retry_delays=NO_WAIT)
    assert str(raised.value) == "Adzuna gb: ReadError"


def test_client_errors_are_not_retried() -> None:
    with client_answering(status(404)) as client, pytest.raises(SourceError) as raised:
        get_json(client, URL, label="Lever acme", retry_delays=NO_WAIT)
    assert str(raised.value) == "Lever acme: HTTP 404"


def maintenance_page(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<html>maintenance</html>")


def test_invalid_json_is_a_source_error() -> None:
    with (
        client_answering(maintenance_page) as client,
        pytest.raises(SourceError, match="not valid JSON"),
    ):
        get_json(client, URL, label="test", retry_delays=NO_WAIT)


def test_errors_never_include_the_url() -> None:
    with client_answering(reset, reset, reset) as client, pytest.raises(SourceError) as raised:
        get_json(client, URL, label="test", retry_delays=NO_WAIT)
    assert "my-secret" not in str(raised.value)
    assert raised.value.__suppress_context__

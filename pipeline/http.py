"""HTTP plumbing shared by the source clients and the LLM backends."""

from __future__ import annotations

import logging
import time
from collections.abc import Collection, Sequence
from typing import Any

import httpx

# httpx logs every request URL at INFO. Adzuna puts its API key in the query string, and
# Airflow keeps INFO logs, so those lines would leak the key.
logging.getLogger("httpx").setLevel(logging.WARNING)

log = logging.getLogger(__name__)

USER_AGENT = "job-insight/0.1 (+https://github.com/Seif-Douida/job-insight)"

RETRY_DELAYS_SECONDS = (2.0, 5.0, 10.0, 20.0, 30.0)
"""Wait before each retry. Adzuna's API resets roughly half of new connections at times
(measured 2026-09-17; other hosts on the same network were unaffected), and a connection
that never opens costs no quota, so several patient retries are cheap and effective."""

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
TOO_MANY_REQUESTS = 429


class HttpError(RuntimeError):
    """A request failed. The message never includes the URL or any credentials.

    `status` and `retry_after` let a caller tell "this request was wrong" from "the server
    is full": only the second is worth waiting out.
    """

    def __init__(
        self, message: str, *, status: int | None = None, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def make_client(timeout_seconds: float = 60.0) -> httpx.Client:
    """HTTP client for the source and model APIs."""
    return httpx.Client(
        timeout=timeout_seconds, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    )


def get_json(
    client: httpx.Client,
    url: str,
    *,
    label: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retry_delays: Sequence[float] = RETRY_DELAYS_SECONDS,
    retry_statuses: Collection[int] = RETRYABLE_STATUSES,
) -> Any:
    """GET a JSON document, retrying transient failures; HttpError labelled `label` otherwise."""
    return _request_json(
        client,
        "GET",
        url,
        label=label,
        params=params,
        headers=headers,
        json_body=None,
        retry_delays=retry_delays,
        retry_statuses=retry_statuses,
    )


def post_json(
    client: httpx.Client,
    url: str,
    *,
    label: str,
    json_body: Any,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retry_delays: Sequence[float] = RETRY_DELAYS_SECONDS,
    retry_statuses: Collection[int] = RETRYABLE_STATUSES,
) -> Any:
    """POST a JSON document and read the JSON answer, with the same retry policy as GET.

    Only used for model APIs, whose calls are idempotent: a retry costs a request, never a
    duplicated side effect.
    """
    return _request_json(
        client,
        "POST",
        url,
        label=label,
        params=params,
        headers=headers,
        json_body=json_body,
        retry_delays=retry_delays,
        retry_statuses=retry_statuses,
    )


def _request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    label: str,
    params: dict[str, Any] | None,
    headers: dict[str, str] | None,
    json_body: Any,
    retry_delays: Sequence[float],
    retry_statuses: Collection[int],
) -> Any:
    attempts = len(retry_delays) + 1
    for attempt in range(1, attempts + 1):
        try:
            response = client.request(method, url, params=params, headers=headers, json=json_body)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status not in retry_statuses or attempt == attempts:
                raise HttpError(
                    f"{label}: HTTP {status}",
                    status=status,
                    retry_after=_retry_after_seconds(error.response),
                ) from None
            reason = f"HTTP {status}"
        except httpx.TransportError as error:
            if attempt == attempts:
                raise HttpError(f"{label}: {type(error).__name__}") from None
            reason = type(error).__name__
        except ValueError:
            raise HttpError(f"{label}: response is not valid JSON") from None
        log.warning("%s: %s, retrying (%d/%d)", label, reason, attempt, attempts - 1)
        time.sleep(retry_delays[attempt - 1])
    raise AssertionError("unreachable")


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """How long the server asked us to wait, if it said so.

    Standard `Retry-After` first, then Google's own form, which is where the Gemini API
    puts it: `error.details[].retryDelay = "22s"`. Only the number is kept, never the
    body, so nothing from a response can reach a log line.
    """
    header = response.headers.get("retry-after", "")
    if header.isdigit():
        return float(header)
    try:
        details = response.json()["error"]["details"]
    except (ValueError, LookupError, TypeError):
        return None
    for detail in details if isinstance(details, list) else []:
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                return None
    return None

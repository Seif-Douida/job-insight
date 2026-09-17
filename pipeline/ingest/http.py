"""HTTP plumbing shared by the source clients."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

import httpx

# httpx logs every request URL at INFO. Adzuna puts its API key in the query string, and
# Airflow keeps INFO logs, so those lines would leak the key.
logging.getLogger("httpx").setLevel(logging.WARNING)

log = logging.getLogger(__name__)

USER_AGENT = "job-insight/0.1 (+https://github.com/Seif-Douida/job-insight)"

RETRY_DELAYS_SECONDS = (2.0, 5.0)
"""Wait before each retry. Sources occasionally reset connections mid-request."""

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class SourceError(RuntimeError):
    """A request to a job source failed. The message never includes the URL or credentials."""


def make_client(timeout_seconds: float = 60.0) -> httpx.Client:
    """HTTP client for the source APIs."""
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
) -> Any:
    """GET a JSON document, retrying transient failures; SourceError labelled `label` otherwise."""
    attempts = len(retry_delays) + 1
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status not in RETRYABLE_STATUSES or attempt == attempts:
                raise SourceError(f"{label}: HTTP {status}") from None
            reason = f"HTTP {status}"
        except httpx.TransportError as error:
            if attempt == attempts:
                raise SourceError(f"{label}: {type(error).__name__}") from None
            reason = type(error).__name__
        except ValueError:
            raise SourceError(f"{label}: response is not valid JSON") from None
        log.warning("%s: %s, retrying (%d/%d)", label, reason, attempt, attempts - 1)
        time.sleep(retry_delays[attempt - 1])
    raise AssertionError("unreachable")

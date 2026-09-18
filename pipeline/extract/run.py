"""Run extraction over stored postings, inside the free-tier quota.

Unlike ingestion, this commits as it goes: a run can take hours, and a crash must not
throw away finished work or lose count of the requests already spent.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any

import psycopg
from psycopg.types.json import Json
from pydantic import ValidationError

from pipeline.extract.llm.base import LlmBackend, ModelError
from pipeline.extract.prompt import PROMPT_VERSION, build_prompt, response_schema
from pipeline.extract.quota import DailyQuota, Pacer, estimate_tokens
from pipeline.extract.schema import Extraction
from pipeline.http import TOO_MANY_REQUESTS, HttpError

log = logging.getLogger(__name__)

DEFAULT_WORKERS = 5
"""Enough to keep the pacer busy at ~25s per call without overshooting the rate limit."""

MAX_ATTEMPTS_PER_POSTING = 3
COMMIT_EVERY = 20
MAX_ERROR_CHARS = 500

RATE_LIMITED = "rate_limited"
"""Outcome for a posting the provider refused to look at. It is never stored: the posting
stays pending, unmarked, because a rate limit is a fact about the minute, not the posting.
Storing it would spend one of its three attempts on something it did not do."""

RATE_LIMIT_PAUSE_SECONDS = 30.0
"""Used only when the provider refuses without saying how long to wait."""

EXTRACTED_TEXT_QUALITY = "full"
"""Only full-text postings are sent to the model. An excerpt is ~500 characters of
"About us" blurb that names no skills, so extracting it would spend quota to learn
nothing; excerpts get their role from `role_hint` instead."""

_PENDING = """
select p.id, p.title, p.company, p.location_raw, p.description_text, p.content_hash
from raw.postings p
left join raw.extractions e
    on e.posting_id = p.id
   and e.model = %(model)s
   and e.prompt_version = %(prompt_version)s
   and e.content_hash = p.content_hash
where p.duplicate_of is null
  and p.text_quality = %(text_quality)s
  and coalesce(p.description_text, '') <> ''
  and (e.id is null or (e.status <> 'ok' and e.attempts < %(max_attempts)s))
order by p.posted_at desc nulls last
limit %(limit)s
"""

_RECORD = """
insert into raw.extractions (
    posting_id, model, prompt_version, content_hash, payload, status, error,
    input_tokens, output_tokens, latency_ms
)
values (
    %(posting_id)s, %(model)s, %(prompt_version)s, %(content_hash)s, %(payload)s,
    %(status)s, %(error)s, %(input_tokens)s, %(output_tokens)s, %(latency_ms)s
)
on conflict (posting_id, model, prompt_version, content_hash) do update set
    payload = excluded.payload,
    status = excluded.status,
    error = excluded.error,
    input_tokens = excluded.input_tokens,
    output_tokens = excluded.output_tokens,
    latency_ms = excluded.latency_ms,
    extracted_at = now(),
    attempts = raw.extractions.attempts + 1
"""


@dataclass(frozen=True)
class ExtractionRun:
    """What one extraction run did; returned to Airflow as the task result."""

    model: str
    pending: int
    granted: int
    ok: int
    invalid: int
    failed: int
    rate_limited: int

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


def extract_pending(
    conn: psycopg.Connection,
    backend: LlmBackend,
    *,
    limit: int,
    prompt_version: str = PROMPT_VERSION,
    quota: DailyQuota | None = None,
    pacer: Pacer | None = None,
    workers: int = DEFAULT_WORKERS,
) -> ExtractionRun:
    """Extract up to `limit` postings that have no successful extraction yet."""
    quota = quota or DailyQuota(backend.name)
    pacer = pacer or Pacer()
    postings = _pending(conn, backend.name, prompt_version, limit)
    granted = quota.reserve(conn, len(postings))
    conn.commit()

    schema = response_schema()
    counts = {"ok": 0, "invalid_json": 0, "error": 0, RATE_LIMITED: 0}
    written = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_extract_one, backend, pacer, posting, schema, prompt_version)
            for posting in postings[:granted]
        ]
        for future in as_completed(futures):
            record = future.result()
            counts[record["status"]] += 1
            if record["status"] == RATE_LIMITED:
                continue
            conn.execute(_RECORD, record)
            written += 1
            if written % COMMIT_EVERY == 0:
                conn.commit()
    quota.release(conn, counts[RATE_LIMITED])
    conn.commit()

    result = ExtractionRun(
        model=backend.name,
        pending=len(postings),
        granted=granted,
        ok=counts["ok"],
        invalid=counts["invalid_json"],
        failed=counts["error"],
        rate_limited=counts[RATE_LIMITED],
    )
    log.info("%s", result)
    return result


def _pending(
    conn: psycopg.Connection, model: str, prompt_version: str, limit: int
) -> list[tuple[Any, ...]]:
    return conn.execute(
        _PENDING,
        {
            "model": model,
            "prompt_version": prompt_version,
            "text_quality": EXTRACTED_TEXT_QUALITY,
            "max_attempts": MAX_ATTEMPTS_PER_POSTING,
            "limit": limit,
        },
    ).fetchall()


def _extract_one(
    backend: LlmBackend,
    pacer: Pacer,
    posting: tuple[Any, ...],
    schema: dict[str, Any],
    prompt_version: str,
) -> dict[str, Any]:
    """Send one posting to the model and turn the answer into a row for raw.extractions."""
    posting_id, title, company, location, description, content_hash = posting
    prompt = build_prompt(title=title, company=company, location=location, description=description)
    row: dict[str, Any] = {
        "posting_id": posting_id,
        "model": backend.name,
        "prompt_version": prompt_version,
        "content_hash": content_hash,
        "payload": None,
        "status": "error",
        "error": None,
        "input_tokens": None,
        "output_tokens": None,
        "latency_ms": None,
    }

    pacer.wait(estimate_tokens(prompt))
    started = time.monotonic()
    try:
        answer = backend.generate(prompt, schema)
    except (HttpError, ModelError) as error:
        row["latency_ms"] = int((time.monotonic() - started) * 1000)
        if isinstance(error, HttpError) and error.status == TOO_MANY_REQUESTS:
            pause = error.retry_after or RATE_LIMIT_PAUSE_SECONDS
            log.warning("Rate limited; holding every worker for %.0fs", pause)
            pacer.pause(pause)
            row["status"] = RATE_LIMITED
            return row
        row["error"] = str(error)[:MAX_ERROR_CHARS]
        return row

    row["latency_ms"] = int((time.monotonic() - started) * 1000)
    row["input_tokens"] = answer.input_tokens
    row["output_tokens"] = answer.output_tokens
    try:
        extraction = Extraction.model_validate_json(answer.text)
    except ValidationError as error:
        row["status"] = "invalid_json"
        row["error"] = str(error)[:MAX_ERROR_CHARS]
        return row

    row["status"] = "ok"
    row["payload"] = Json(extraction.model_dump(mode="json"))
    return row

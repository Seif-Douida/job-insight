"""Archiving keeps Neon small without losing the text a better model could re-read."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import psycopg

from pipeline.extract.archive import KEEP_CHARS, archive_and_trim
from pipeline.ingest.posting import RawPosting
from pipeline.ingest.store import upsert_postings

MODEL = "fake-model"
PROMPT_VERSION = "v1"
LONG_TEXT = ("Pipelines and Python. " * 200).strip()  # RawPosting strips outer whitespace


def store_extracted_posting(db: psycopg.Connection, *, description: str = LONG_TEXT) -> str:
    posting = RawPosting(
        source="greenhouse",
        source_id="1",
        url="https://example.com/1",
        title="Data Engineer",
        company="Acme",
        country="GB",
        description_text=description,
    )
    upsert_postings(db, [posting])
    db.execute(
        """
        insert into raw.extractions
            (posting_id, model, prompt_version, content_hash, payload, status)
        select id, %s, %s, content_hash, '{}'::jsonb, 'ok' from raw.postings
        """,
        (MODEL, PROMPT_VERSION),
    )
    return posting.content_hash


def stored_text(db: psycopg.Connection) -> str:
    return db.execute("select description_text from raw.postings").fetchone()[0]


def test_archives_full_text_then_trims_the_stored_copy(
    db: psycopg.Connection, tmp_path: Path
) -> None:
    content_hash = store_extracted_posting(db)

    trimmed = archive_and_trim(db, model=MODEL, prompt_version=PROMPT_VERSION, archive_dir=tmp_path)

    assert trimmed == 1
    assert len(stored_text(db)) == KEEP_CHARS
    archive = next(tmp_path.glob("postings-*.jsonl.gz"))
    with gzip.open(archive, "rt", encoding="utf-8") as handle:
        record = json.loads(handle.readline())
    assert record["description_text"] == LONG_TEXT
    assert (record["content_hash"], record["source"]) == (content_hash, "greenhouse")


def test_running_again_finds_nothing_to_do(db: psycopg.Connection, tmp_path: Path) -> None:
    store_extracted_posting(db)
    archive_and_trim(db, model=MODEL, prompt_version=PROMPT_VERSION, archive_dir=tmp_path)

    assert (
        archive_and_trim(db, model=MODEL, prompt_version=PROMPT_VERSION, archive_dir=tmp_path) == 0
    )


def test_short_postings_are_left_alone(db: psycopg.Connection, tmp_path: Path) -> None:
    store_extracted_posting(db, description="Short posting.")

    assert (
        archive_and_trim(db, model=MODEL, prompt_version=PROMPT_VERSION, archive_dir=tmp_path) == 0
    )
    assert stored_text(db) == "Short posting."


def test_postings_without_a_successful_extraction_keep_their_text(
    db: psycopg.Connection, tmp_path: Path
) -> None:
    store_extracted_posting(db)
    db.execute("update raw.extractions set status = 'error'")

    assert (
        archive_and_trim(db, model=MODEL, prompt_version=PROMPT_VERSION, archive_dir=tmp_path) == 0
    )
    assert len(stored_text(db)) == len(LONG_TEXT)

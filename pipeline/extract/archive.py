"""Archive full descriptions to disk, then trim what the database keeps.

Neon's free tier is 0.5 GB and descriptions are most of it. They are only needed until a
posting has been extracted, so the full text is appended to a monthly gzipped JSONL file
under data/archive/ (kept out of git) and the stored copy is cut to KEEP_CHARS. A better
model can re-extract from the archive later.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from pipeline.config import REPO_ROOT
from pipeline.extract.prompt import PROMPT_VERSION

log = logging.getLogger(__name__)

ARCHIVE_DIR = REPO_ROOT / "data" / "archive"
KEEP_CHARS = 1000

_EXTRACTED_AND_LONG = """
select p.id, p.source, p.source_id, p.url, p.content_hash, p.description_text
from raw.postings p
join raw.extractions e
    on e.posting_id = p.id
   and e.model = %(model)s
   and e.prompt_version = %(prompt_version)s
   and e.content_hash = p.content_hash
   and e.status = 'ok'
where length(p.description_text) > %(keep_chars)s
limit %(batch)s
"""


def archive_and_trim(
    conn: psycopg.Connection,
    *,
    model: str,
    prompt_version: str = PROMPT_VERSION,
    batch: int = 500,
    archive_dir: Path = ARCHIVE_DIR,
) -> int:
    """Archive and trim already-extracted postings; returns how many were trimmed."""
    rows = conn.execute(
        _EXTRACTED_AND_LONG,
        {
            "model": model,
            "prompt_version": prompt_version,
            "keep_chars": KEEP_CHARS,
            "batch": batch,
        },
    ).fetchall()
    if not rows:
        return 0

    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"postings-{datetime.now(UTC):%Y-%m}.jsonl.gz"
    with gzip.open(path, "at", encoding="utf-8") as archive:
        for posting_id, source, source_id, url, content_hash, description in rows:
            archive.write(
                json.dumps(
                    {
                        "posting_id": posting_id,
                        "source": source,
                        "source_id": source_id,
                        "url": url,
                        "content_hash": content_hash,
                        "description_text": description,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    conn.execute(
        "update raw.postings set description_text = left(description_text, %s) where id = any(%s)",
        (KEEP_CHARS, [row[0] for row in rows]),
    )
    log.info("Archived and trimmed %d postings into %s", len(rows), path.name)
    return len(rows)

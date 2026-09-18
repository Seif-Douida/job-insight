"""Build the golden set: join the hand-written labels with the postings they describe.

    python -m pipeline.eval.build_golden_set

Reads labels.json, pulls each posting's stored text from the database, and writes
golden_set.jsonl. The evaluation sends exactly the text saved here, so the model sees
what the labeller read.

Text already in golden_set.jsonl is kept as it is: postings are trimmed in the database
once they have been extracted, and re-reading a trimmed posting would quietly invalidate
its labels. Only postings new to the file are read from the database.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.db import connect

EVAL_DIR = Path(__file__).resolve().parent
LABELS_PATH = EVAL_DIR / "labels.json"
GOLDEN_SET_PATH = EVAL_DIR / "golden_set.jsonl"

DESCRIPTION_CHARS = 3500
"""How much of each posting the labeller read, and the evaluation sends."""


def existing_postings() -> dict[int, dict[str, Any]]:
    if not GOLDEN_SET_PATH.exists():
        return {}
    with GOLDEN_SET_PATH.open(encoding="utf-8") as handle:
        return {json.loads(line)["id"]: json.loads(line) for line in handle if line.strip()}


def main() -> None:
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))["labels"]
    posting_ids = [int(key) for key in labels]
    postings = existing_postings()
    wanted = [posting_id for posting_id in posting_ids if posting_id not in postings]

    if wanted:
        with connect() as conn:
            rows = conn.execute(
                """
                select id, title, company, location_raw, left(description_text, %s)
                from raw.postings where id = any(%s)
                """,
                (DESCRIPTION_CHARS, wanted),
            ).fetchall()
        missing = set(wanted) - {row[0] for row in rows}
        if missing:
            raise RuntimeError(f"Labelled postings are not in the database: {sorted(missing)}")
        for posting_id, title, company, location, description in rows:
            postings[posting_id] = {
                "id": posting_id,
                "title": title,
                "company": company,
                "location": location,
                "description": description,
            }

    with GOLDEN_SET_PATH.open("w", encoding="utf-8") as out:
        for posting_id in sorted(posting_ids):
            entry = dict(postings[posting_id], labels=labels[str(posting_id)])
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"wrote {len(posting_ids)} postings to {GOLDEN_SET_PATH} ({len(wanted)} newly read)")


if __name__ == "__main__":
    main()

"""Writes postings to raw.postings and links copies of the same job across sources.

Functions here never commit: the caller owns the transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import psycopg

from pipeline.ingest.posting import AGGREGATOR_SOURCES, RawPosting

_UPSERT = """
insert into raw.postings (
    source, source_id, url, title, company, location_raw, country, region, role_hint,
    description_text, text_quality, posted_at, salary_min, salary_max, salary_currency,
    salary_is_predicted, content_hash, dedupe_key
)
values (
    %(source)s, %(source_id)s, %(url)s, %(title)s, %(company)s, %(location_raw)s,
    %(country)s, %(region)s, %(role_hint)s, %(description_text)s, %(text_quality)s,
    %(posted_at)s, %(salary_min)s, %(salary_max)s, %(salary_currency)s,
    %(salary_is_predicted)s, %(content_hash)s, %(dedupe_key)s
)
on conflict (source, source_id) do update set
    url = excluded.url,
    title = excluded.title,
    company = excluded.company,
    location_raw = excluded.location_raw,
    country = excluded.country,
    region = excluded.region,
    role_hint = excluded.role_hint,
    description_text = excluded.description_text,
    text_quality = excluded.text_quality,
    posted_at = excluded.posted_at,
    salary_min = excluded.salary_min,
    salary_max = excluded.salary_max,
    salary_currency = excluded.salary_currency,
    salary_is_predicted = excluded.salary_is_predicted,
    content_hash = excluded.content_hash,
    dedupe_key = excluded.dedupe_key
where raw.postings.content_hash <> excluded.content_hash
   or raw.postings.dedupe_key <> excluded.dedupe_key
returning (xmax = 0) as inserted
"""

_LINK_DUPLICATES = """
with ranked as (
    select id,
           source,
           first_value(id) over same_job as canonical_id,
           first_value(source) over same_job as canonical_source
    from raw.postings
    window same_job as (
        partition by dedupe_key
        order by source = any(%(aggregators)s), text_quality = 'full' desc, id
    )
),
resolved as (
    select id,
           case
               when id = canonical_id then null
               when source <> canonical_source then canonical_id
               when source = any(%(aggregators)s) then canonical_id
           end as duplicate_of
    from ranked
)
update raw.postings as posting
set duplicate_of = resolved.duplicate_of
from resolved
where posting.id = resolved.id
  and posting.duplicate_of is distinct from resolved.duplicate_of
"""


@dataclass(frozen=True)
class UpsertCounts:
    inserted: int
    updated: int


def upsert_postings(conn: psycopg.Connection, postings: Sequence[RawPosting]) -> UpsertCounts:
    """Insert new postings and update changed ones. Unchanged postings are not touched."""
    inserted = updated = 0
    if not postings:
        return UpsertCounts(inserted, updated)
    with conn.cursor() as cursor:
        cursor.executemany(_UPSERT, [_row(posting) for posting in postings], returning=True)
        while True:
            row = cursor.fetchone()  # one row if written, none if unchanged
            if row is not None:
                if row[0]:
                    inserted += 1
                else:
                    updated += 1
            if not cursor.nextset():
                break
    return UpsertCounts(inserted, updated)


def link_duplicates(conn: psycopg.Connection) -> int:
    """Point every duplicate posting at its canonical copy; returns the rows changed.

    Canonical copy preference: a company job board over an aggregator, then full text over
    an excerpt, then the earliest stored. Two job-board postings with the same title stay
    separate (distinct openings), while an aggregator's reposts of one job collapse.
    """
    with conn.cursor() as cursor:
        cursor.execute(_LINK_DUPLICATES, {"aggregators": sorted(AGGREGATOR_SOURCES)})
        return cursor.rowcount


def _row(posting: RawPosting) -> dict[str, Any]:
    return {
        **posting.model_dump(),
        "region": posting.region,
        "role_hint": posting.role_hint,
        "text_quality": posting.text_quality,
        "content_hash": posting.content_hash,
        "dedupe_key": posting.dedupe_key,
    }

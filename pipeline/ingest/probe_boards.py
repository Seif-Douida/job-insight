"""Find which public job board (Greenhouse, Lever, Ashby) companies publish on.

Used to grow companies.yaml. For each slug, tries every board type and prints how many
postings are listed and how many would be stored (a curated role in a curated region).
Slugs are probed concurrently; lines print as each finishes.

    python -m pipeline.ingest.probe_boards stripe spotify openai
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

import httpx

from pipeline.http import HttpError, make_client
from pipeline.ingest import smartrecruiters
from pipeline.ingest.run import BOARD_SOURCES, in_scope, parse_items

WORKERS = 8

SURVEYS = {"smartrecruiters": smartrecruiters.survey}
"""Boards that can be counted without downloading every description. Fetching a
SmartRecruiters board costs one request per posting, which is far too much for a probe."""


def probe(client: httpx.Client, slug: str) -> list[str]:
    """One report line per board type that has postings for `slug`."""
    lines = []
    for ats, (fetch, parse) in BOARD_SOURCES.items():
        try:
            if ats in SURVEYS:
                listed, kept = SURVEYS[ats](client, slug)
            else:
                items = fetch(client, slug)
                postings, _ = parse_items(items, partial(parse, company=slug))
                listed = len(items)
                kept = sum(1 for posting in postings if in_scope(posting))
        except (HttpError, KeyError, TypeError):
            continue
        if listed:
            lines.append(f"{slug:<28} {ats:<11} listed={listed:<5} in_scope={kept}")
    return lines


def main(slugs: list[str]) -> None:
    with make_client() as client, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(probe, client, slug) for slug in slugs]
        for future in as_completed(futures):
            for line in future.result():
                print(line, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

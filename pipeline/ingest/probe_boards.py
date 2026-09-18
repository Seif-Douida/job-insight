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
from pipeline.ingest.run import BOARD_SOURCES, in_scope, parse_items

WORKERS = 8


def probe(client: httpx.Client, slug: str) -> list[str]:
    """One report line per board type that has postings for `slug`."""
    lines = []
    for ats, (fetch, parse) in BOARD_SOURCES.items():
        try:
            items = fetch(client, slug)
        except (HttpError, KeyError, TypeError):
            continue
        if not items:
            continue
        postings, _ = parse_items(items, partial(parse, company=slug))
        kept = sum(1 for posting in postings if in_scope(posting))
        lines.append(f"{slug:<28} {ats:<11} listed={len(items):<5} in_scope={kept}")
    return lines


def main(slugs: list[str]) -> None:
    with make_client() as client, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(probe, client, slug) for slug in slugs]
        for future in as_completed(futures):
            for line in future.result():
                print(line, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

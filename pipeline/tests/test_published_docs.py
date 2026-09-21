"""The methodology page ships a copy of `docs/methodology.md`, and a copy can drift.

The dashboard deploys as `web/` alone — Vercel needs `web/package.json` at the root of the
project to recognise Next.js at all — so the page cannot read a file that lives a level
above it. The copy under `web/content/` is therefore committed, and refreshed by
`web/scripts/sync-docs.mjs` whenever the original is to hand.

That makes a second copy of a document whose entire purpose is to be an accurate account of
how the numbers were produced. A methodology that has quietly fallen behind the method is
worse than none at all, so the two are compared here: edit `docs/methodology.md`, run any
build of the dashboard, and commit both.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ORIGINAL = REPO / "docs" / "methodology.md"
PUBLISHED = REPO / "web" / "content" / "methodology.md"

REFRESH = "cd web && npm run prebuild"


def test_the_published_methodology_exists() -> None:
    assert PUBLISHED.exists(), (
        f"{PUBLISHED.relative_to(REPO)} is missing, so /methodology would be empty. "
        f"Regenerate it: {REFRESH}"
    )


def test_the_published_methodology_matches_the_original() -> None:
    original = ORIGINAL.read_text(encoding="utf-8")
    published = PUBLISHED.read_text(encoding="utf-8")
    assert published == original, (
        "web/content/methodology.md has drifted from docs/methodology.md. The site would "
        f"describe a method the project no longer follows. Regenerate it: {REFRESH}"
    )

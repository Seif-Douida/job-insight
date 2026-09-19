"""The dashboard writes down its own role and region names, and this keeps them honest.

`web/lib/taxonomy.ts` holds display labels so the web app does not need a YAML parser for
eleven strings. That is a copy, and a copy drifts: rename a role in `roles.yaml` and the
site would go on showing the old name with no error anywhere. These tests fail instead.

The pipeline's YAML is the source of truth in both directions - a slug the site does not
know would render as a raw slug, and a slug the site knows but the pipeline does not is a
label left behind by a rename.
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline.taxonomy import load_regions, load_roles

TAXONOMY_TS = Path(__file__).resolve().parents[2] / "web" / "lib" / "taxonomy.ts"

ENTRY = re.compile(r'^\s*"?([a-z-]+)"?:\s*"([^"]+)",', re.MULTILINE)


def read_map(name: str) -> dict[str, str]:
    """Pull one `export const NAME = { ... }` object out of the TypeScript source."""
    source = TAXONOMY_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name}[^=]*=\s*\{{(.*?)\n\}};", source, re.DOTALL)
    assert match, f"{name} is not declared in {TAXONOMY_TS.name}"
    return dict(ENTRY.findall(match.group(1)))


def test_role_labels_match_the_taxonomy() -> None:
    expected = {role.slug: role.label for role in load_roles()}
    assert read_map("ROLE_LABELS") == expected


def test_region_labels_match_the_taxonomy() -> None:
    assert read_map("REGION_LABELS") == load_regions()


def test_every_region_has_a_short_name_and_a_prose_form() -> None:
    slugs = set(load_regions())
    assert set(read_map("REGION_SHORT")) == slugs
    assert set(read_map("REGION_IN")) == slugs


def test_matrix_lists_every_role_and_region_exactly_once() -> None:
    """The front page draws the matrix from these orders, so a missing slug is a hole."""
    source = TAXONOMY_TS.read_text(encoding="utf-8")

    def read_order(name: str) -> list[str]:
        match = re.search(rf"export const {name}\s*=\s*\[(.*?)\];", source, re.DOTALL)
        assert match, f"{name} is not declared in {TAXONOMY_TS.name}"
        return re.findall(r'"([a-z-]+)"', match.group(1))

    roles = read_order("ROLE_ORDER")
    regions = read_order("REGION_ORDER")
    assert sorted(roles) == sorted(role.slug for role in load_roles())
    assert sorted(regions) == sorted(load_regions())

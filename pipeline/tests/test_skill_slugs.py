"""Two skills must never share a URL.

`/skill/[skill]` recovers a skill's name by matching the slug in the URL against the marts,
so if two canonical skills slugify to the same string one of them becomes unreachable and
the other silently answers for both. Stripping punctuation would do exactly that to `C++`
and `C#`, which is why the slug spells those two characters out.

The rule lives in `web/lib/slug.ts`; it is restated here because the canonical names it has
to keep apart come from `skill_aliases.csv`, and this is where that file is tested. The
examples below pin the shared behaviour, so a change to one side fails here.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import pytest

SEED = Path(__file__).resolve().parents[1] / "dbt" / "seeds" / "skill_aliases.csv"


def skill_slug(name: str) -> str:
    """The URL form of a skill name. Mirrors `skillSlug` in web/lib/slug.ts."""
    slug = name.lower().replace("+", "-plus").replace("#", "-sharp")
    return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")


def canonical_skills() -> list[str]:
    with SEED.open(encoding="utf-8") as handle:
        return sorted({row["canonical_skill"] for row in csv.DictReader(handle)})


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Python", "python"),
        ("C++", "c-plus-plus"),
        ("C#", "c-sharp"),
        ("C", "c"),
        ("A/B testing", "a-b-testing"),
        ("CI/CD", "ci-cd"),
        (".NET", "net"),
        ("Hugging Face", "hugging-face"),
    ],
)
def test_slug_examples(name: str, expected: str) -> None:
    assert skill_slug(name) == expected


def test_no_two_canonical_skills_share_a_slug() -> None:
    by_slug: dict[str, list[str]] = defaultdict(list)
    for skill in canonical_skills():
        by_slug[skill_slug(skill)].append(skill)
    collisions = {slug: names for slug, names in by_slug.items() if len(names) > 1}
    assert not collisions, f"these skills would share one page: {collisions}"


def test_no_canonical_skill_slugs_to_nothing() -> None:
    """A name made only of punctuation would produce an empty slug and a broken URL."""
    empty = [skill for skill in canonical_skills() if not skill_slug(skill)]
    assert not empty


def test_canonical_names_are_not_duplicated_by_case_or_punctuation() -> None:
    """`Hugging Face` and `HuggingFace` are one skill; two rows would split its percentage.

    This is the failure the alias table exists to prevent, and it happened twice before it
    was tested for. Real distinctions such as C, C# and C++ survive because the check keeps
    `#` and `+`.
    """
    by_key: dict[str, set[str]] = defaultdict(set)
    for skill in canonical_skills():
        key = re.sub(r"[^a-z0-9#+]", "", skill.lower())
        by_key[key].add(skill)
    duplicates = {key: names for key, names in by_key.items() if len(names) > 1}
    assert not duplicates, f"these are the same skill written two ways: {duplicates}"

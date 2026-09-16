"""Loading and matching of the curated role and region taxonomies.

The YAML files next to this module are the single source of truth for which roles and
regions exist. Everything downstream (ingestion, extraction, dbt seeds) reads them here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

TAXONOMY_DIR = Path(__file__).resolve().parent
OTHER_REGION = "other"

_PUNCTUATION = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Role:
    """A curated role and the title patterns that identify it."""

    slug: str
    label: str
    match: tuple[str, ...]
    exclude: tuple[str, ...]


@dataclass(frozen=True)
class Country:
    """A country we collect postings from, and the region it rolls up into."""

    code: str
    name: str
    region: str
    adzuna: str | None


def normalize_title(title: str) -> str:
    """Lowercase a title and reduce punctuation to single spaces.

    The result is padded with spaces so patterns like `"chief "` match at the start.
    """
    return f" {_PUNCTUATION.sub(' ', title.lower()).strip()} "


def _load_yaml(filename: str) -> dict[str, Any]:
    return yaml.safe_load((TAXONOMY_DIR / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_roles() -> tuple[Role, ...]:
    """Curated roles, in the order they should be matched."""
    return tuple(
        Role(
            slug=entry["slug"],
            label=entry["label"],
            match=tuple(entry.get("match", ())),
            exclude=tuple(entry.get("exclude", ())),
        )
        for entry in _load_yaml("roles.yaml")["roles"]
    )


@lru_cache(maxsize=1)
def load_global_excludes() -> tuple[str, ...]:
    """Title fragments that disqualify a posting from every curated role."""
    return tuple(_load_yaml("roles.yaml").get("global_exclude", ()))


def match_role(title: str) -> str | None:
    """Return the slug of the first role whose patterns match `title`, else None.

    A None result means the title needs the LLM classifier, not that it has no role.
    """
    normalized = normalize_title(title)
    if any(fragment in normalized for fragment in load_global_excludes()):
        return None
    for role in load_roles():
        if any(fragment in normalized for fragment in role.exclude):
            continue
        if any(fragment in normalized for fragment in role.match):
            return role.slug
    return None


@lru_cache(maxsize=1)
def load_countries() -> dict[str, Country]:
    """Every collected country, keyed by ISO 3166-1 alpha-2 code."""
    regions = _load_yaml("regions.yaml")["regions"]
    return {
        entry["code"]: Country(
            code=entry["code"],
            name=entry["name"],
            region=slug,
            adzuna=entry.get("adzuna"),
        )
        for slug, region in regions.items()
        for entry in region["countries"]
    }


@lru_cache(maxsize=1)
def load_regions() -> dict[str, str]:
    """Region slug to display label."""
    return {slug: region["label"] for slug, region in _load_yaml("regions.yaml")["regions"].items()}


def region_for_country(code: str | None) -> str:
    """Region a country rolls up into; `other` for anything outside the taxonomy."""
    if not code:
        return OTHER_REGION
    country = load_countries().get(code.upper())
    return country.region if country else OTHER_REGION

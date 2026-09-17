"""Curated roles, and deciding which job titles belong to them."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from pipeline.taxonomy._files import read_yaml

_PUNCTUATION = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Role:
    """A curated role, the phrase used to search for it, and its title patterns."""

    slug: str
    label: str
    search: str
    match: tuple[str, ...]
    exclude: tuple[str, ...] = ()


def normalize_title(title: str) -> str:
    """Lowercase a title and reduce punctuation to single spaces, padded with spaces.

    The padding lets patterns such as `" ai "` match whole words at either end.
    """
    return f" {_PUNCTUATION.sub(' ', title.lower()).strip()} "


@cache
def load_roles() -> tuple[Role, ...]:
    """Curated roles, in the order they should be matched."""
    return tuple(
        Role(
            slug=entry["slug"],
            label=entry["label"],
            search=entry["search"],
            match=tuple(entry["match"]),
            exclude=tuple(entry.get("exclude", ())),
        )
        for entry in read_yaml("roles.yaml")["roles"]
    )


def get_role(slug: str) -> Role:
    """The curated role with this slug; KeyError if there is none."""
    for role in load_roles():
        if role.slug == slug:
            return role
    raise KeyError(slug)


def match_role(title: str) -> str | None:
    """Slug of the first role whose patterns match `title`, else None.

    None means the title needs the LLM classifier, not that it has no role.
    """
    normalized = normalize_title(title)
    if _is_globally_excluded(normalized):
        return None
    for role in load_roles():
        if _contains_any(normalized, role.match) and not _contains_any(normalized, role.exclude):
            return role.slug
    return None


def is_relevant_title(title: str) -> bool:
    """Whether a posting is worth storing: it matches a curated role, or plausibly could.

    "Software Engineer, Data Infrastructure" matches no role pattern but may still be a
    Data Engineer role; the LLM classifier settles those later.
    """
    normalized = normalize_title(title)
    if _is_globally_excluded(normalized):
        return False
    keywords = read_yaml("roles.yaml")["relevance_keywords"]
    return match_role(title) is not None or _contains_any(normalized, keywords)


def _is_globally_excluded(normalized_title: str) -> bool:
    return _contains_any(normalized_title, read_yaml("roles.yaml")["global_exclude"])


def _contains_any(normalized_title: str, fragments: Iterable[str]) -> bool:
    return any(fragment in normalized_title for fragment in fragments)

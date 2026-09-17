"""Regions, the countries in them, and recognizing those countries in free-text locations."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from pipeline.taxonomy._files import read_yaml

OTHER_REGION = "other"


@dataclass(frozen=True)
class AdzunaMarket:
    """An Adzuna country market, and how many result pages to fetch per role."""

    country: str
    market: str
    currency: str
    pages: int


@dataclass(frozen=True)
class Country:
    """A country we collect postings from, and the ways locations name it."""

    code: str
    name: str
    region: str
    aliases: tuple[str, ...] = ()
    codes: tuple[str, ...] = ()
    state_codes: tuple[str, ...] = ()
    adzuna: AdzunaMarket | None = None
    jsearch: bool = False


@cache
def load_countries() -> dict[str, Country]:
    """Every collected country, keyed by ISO 3166-1 alpha-2 code."""
    countries: dict[str, Country] = {}
    for region_slug, region in read_yaml("regions.yaml")["regions"].items():
        for entry in region["countries"]:
            code = entry["code"]
            if code in countries:
                raise ValueError(f"Country {code} is listed twice in regions.yaml")
            adzuna = entry.get("adzuna")
            countries[code] = Country(
                code=code,
                name=entry["name"],
                region=region_slug,
                aliases=tuple(entry.get("aliases", ())),
                codes=tuple(entry.get("codes", ())),
                state_codes=tuple(entry.get("state_codes", ())),
                adzuna=AdzunaMarket(country=code, **adzuna) if adzuna else None,
                jsearch=entry.get("jsearch", False),
            )
    return countries


@cache
def load_regions() -> dict[str, str]:
    """Region slug to display label."""
    return {slug: region["label"] for slug, region in read_yaml("regions.yaml")["regions"].items()}


def get_country(code: str) -> Country:
    """The curated country with this ISO code; KeyError if there is none."""
    return load_countries()[code.upper()]


def region_for_country(code: str | None) -> str:
    """Region a country rolls up into; `other` for anything outside the taxonomy."""
    country = load_countries().get(code.upper()) if code else None
    return country.region if country else OTHER_REGION


def adzuna_markets() -> tuple[AdzunaMarket, ...]:
    """Adzuna markets to query, one per country Adzuna serves."""
    return tuple(country.adzuna for country in load_countries().values() if country.adzuna)


def jsearch_countries() -> tuple[Country, ...]:
    """Countries to query through JSearch."""
    return tuple(country for country in load_countries().values() if country.jsearch)


def resolve_country(location: str | None) -> str | None:
    """ISO code of the first curated country a free-text location names, else None.

    "Dublin, London" names two places and the earlier one wins. Places outside the
    taxonomy ("Toronto", "Singapore") resolve to None rather than being guessed.
    """
    if not location:
        return None
    earliest: tuple[int, str] | None = None
    for pattern, code in _location_patterns():
        found = pattern.search(location)
        if found and (earliest is None or found.start() < earliest[0]):
            earliest = (found.start(), code)
    return earliest[1] if earliest else None


@cache
def _location_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    patterns: list[tuple[re.Pattern[str], str]] = []
    for country in load_countries().values():
        if country.aliases:
            patterns.append((_whole_words(country.aliases, re.IGNORECASE), country.code))
        if country.codes:
            patterns.append((_whole_words(country.codes), country.code))
        if country.state_codes:
            states = "|".join(country.state_codes)
            patterns.append((re.compile(rf",\s*(?:{states})(?!\w)"), country.code))
    return tuple(patterns)


def _whole_words(terms: Iterable[str], flags: int = 0) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", flags)

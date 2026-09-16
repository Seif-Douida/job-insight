"""The taxonomy decides which postings count toward which role and region,
so its loading and matching rules are tested before anything depends on them."""

from __future__ import annotations

import pytest

from pipeline.taxonomy import (
    OTHER_REGION,
    load_countries,
    load_regions,
    load_roles,
    match_role,
    normalize_title,
    region_for_country,
)


def test_role_slugs_are_unique() -> None:
    slugs = [role.slug for role in load_roles()]
    assert len(slugs) == len(set(slugs))


def test_every_role_has_patterns() -> None:
    assert all(role.match for role in load_roles())


def test_normalize_title_strips_punctuation_and_pads() -> None:
    assert normalize_title("Sr. Data-Engineer (Remote)") == " sr data engineer remote "


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Data Engineer", "data-engineer"),
        ("Data Platform Engineer, Streaming", "data-engineer"),
        ("Analytics Engineer (dbt)", "analytics-engineer"),
        ("Machine Learning Engineer - NLP", "ml-engineer"),
        ("MLOps Engineer", "mlops-engineer"),
        ("AI Engineer, LLM Platform", "ai-engineer"),
        ("Data Scientist II", "data-scientist"),
        ("Business Intelligence Analyst", "data-analyst"),
    ],
)
def test_match_role_assigns_expected_slug(title: str, expected: str) -> None:
    assert match_role(title) == expected


@pytest.mark.parametrize(
    "title",
    [
        "Head of Data Engineering",  # global exclude: leadership
        "VP of Machine Learning",
        "Technical Recruiter, Data",
        "Data Engineering Manager",  # role-level exclude: manager
        "Data Entry Clerk",  # role-level exclude: not a data role
        "Frontend Engineer",  # no curated role matches
    ],
)
def test_match_role_rejects_out_of_scope_titles(title: str) -> None:
    assert match_role(title) is None


def test_specific_roles_match_before_general_ones() -> None:
    """`ml platform engineer` is MLOps, not ML Engineer, so ordering must hold."""
    assert match_role("ML Platform Engineer") == "mlops-engineer"


def test_countries_roll_up_into_declared_regions() -> None:
    assert region_for_country("US") == "us"
    assert region_for_country("DE") == "eu"
    assert region_for_country("AE") == "gulf"
    assert region_for_country("gb") == "uk"  # case-insensitive


def test_unknown_or_missing_country_is_other() -> None:
    assert region_for_country("JP") == OTHER_REGION
    assert region_for_country(None) == OTHER_REGION


def test_every_country_belongs_to_a_declared_region() -> None:
    regions = load_regions()
    assert {country.region for country in load_countries().values()} <= set(regions)


def test_country_codes_are_unique_across_regions() -> None:
    countries = load_countries()
    assert len(countries) == sum(1 for _ in countries.values())
    assert all(code == country.code for code, country in countries.items())

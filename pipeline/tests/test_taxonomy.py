"""The taxonomy decides which postings are stored and where they count,
so its loading and matching rules are pinned down before anything relies on them."""

from __future__ import annotations

import pytest

from pipeline.taxonomy import (
    BOARD_TYPES,
    OTHER_REGION,
    get_country,
    get_role,
    is_relevant_title,
    load_companies,
    load_countries,
    load_regions,
    load_roles,
    match_role,
    normalize_title,
    region_for_country,
    resolve_country,
)

# --- roles -----------------------------------------------------------------------------


def test_role_slugs_are_unique() -> None:
    slugs = [role.slug for role in load_roles()]
    assert len(slugs) == len(set(slugs))


def test_every_role_has_a_search_phrase_and_patterns() -> None:
    assert all(role.search and role.match for role in load_roles())


def test_get_role_by_slug() -> None:
    assert get_role("data-engineer").label == "Data Engineer"
    with pytest.raises(KeyError):
        get_role("astronaut")


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
        "HTML Engineer",  # " ml engineer" must start at a word
        "Frontend Engineer",  # no curated role matches
    ],
)
def test_match_role_rejects_out_of_scope_titles(title: str) -> None:
    assert match_role(title) is None


def test_specific_roles_match_before_general_ones() -> None:
    """`ml platform engineer` is MLOps, not ML Engineer, so ordering must hold."""
    assert match_role("ML Platform Engineer") == "mlops-engineer"


@pytest.mark.parametrize(
    ("title", "relevant"),
    [
        ("Data Engineer", True),
        ("Software Engineer, Data Infrastructure", True),  # no role pattern, but plausible
        ("Research Engineer, LLM Evaluation", True),
        ("Account Executive, AI Sales", False),  # globally excluded
        ("Abuse Investigator", False),
        ("Database Administrator", False),  # " data " is a whole word
    ],
)
def test_is_relevant_title(title: str, relevant: bool) -> None:
    assert is_relevant_title(title) is relevant


# --- regions ---------------------------------------------------------------------------


def test_countries_roll_up_into_declared_regions() -> None:
    assert region_for_country("US") == "us"
    assert region_for_country("DE") == "eu"
    assert region_for_country("AE") == "gulf"
    assert region_for_country("gb") == "uk"  # case-insensitive


def test_unknown_or_missing_country_is_other() -> None:
    assert region_for_country("JP") == OTHER_REGION
    assert region_for_country(None) == OTHER_REGION


def test_every_country_belongs_to_a_declared_region() -> None:
    assert {country.region for country in load_countries().values()} <= set(load_regions())


def test_get_country_by_code() -> None:
    assert get_country("ae").name == "United Arab Emirates"


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("San Francisco, CA", "US"),
        ("US-Remote", "US"),
        ("Remote - US", "US"),
        ("NYC", "US"),
        ("Cambridge, MA", "US"),  # state code after a comma
        ("Bellevue, Washington", "US"),  # state spelled out, city not in the list
        ("Kansas City, Missouri", "US"),
        ("Portland, Maine", "US"),
        ("United States", "US"),
        ("London, UK", "GB"),
        ("Belfast, Northern Ireland", "GB"),  # not Ireland: the earlier place wins
        ("Dublin, Ireland", "IE"),
        ("Dublin, London", "IE"),
        ("München", "DE"),
        ("Dubai, United Arab Emirates", "AE"),
        ("Riyadh, KSA", "SA"),
        ("Toronto, Canada", None),
        ("Tbilisi, Georgia", None),  # the country, which is why Georgia is not a US alias
        ("Singapore", None),
        ("Latin America", None),
        ("Pune, IN", None),  # India, not Indiana
        ("Tel Aviv, IL", None),  # Israel, not Illinois
        ("N/A", None),
        ("Remote", None),
        ("", None),
        (None, None),
    ],
)
def test_resolve_country(location: str | None, expected: str | None) -> None:
    assert resolve_country(location) == expected


# --- companies -------------------------------------------------------------------------


def test_companies_use_supported_board_types() -> None:
    companies = load_companies()
    assert companies
    assert all(company.ats in BOARD_TYPES for company in companies)

"""RawPosting derives the fields that decide how a posting is counted."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from pipeline.ingest.posting import FULL_TEXT_MIN_CHARS, RawPosting


def make(**overrides: Any) -> RawPosting:
    fields = {
        "source": "greenhouse",
        "source_id": "1",
        "url": "https://example.com/jobs/1",
        "title": "Data Engineer",
        "company": "Acme",
        "country": "GB",
        "description_text": "x" * FULL_TEXT_MIN_CHARS,
    }
    return RawPosting(**(fields | overrides))


def test_long_description_is_full_text() -> None:
    assert make().text_quality == "full"


def test_short_description_is_an_excerpt_whatever_the_source() -> None:
    assert (
        make(source="jsearch", description_text="A 450-character snippet").text_quality == "excerpt"
    )


def test_adzuna_is_always_an_excerpt() -> None:
    assert make(source="adzuna").text_quality == "excerpt"


def test_region_follows_country() -> None:
    assert (make(country="DE").region, make(country="JP").region, make(country=None).region) == (
        "eu",
        "other",
        "other",
    )


def test_dedupe_key_ignores_legal_suffix_case_and_punctuation() -> None:
    board = make(company="Acme Ltd.", title="Senior Data Engineer")
    aggregator = make(source="adzuna", source_id="99", company="ACME", title="Senior data-engineer")
    assert board.dedupe_key == aggregator.dedupe_key


def test_dedupe_key_differs_by_country() -> None:
    assert make(country="GB").dedupe_key != make(country="IE").dedupe_key


def test_postings_without_a_company_are_never_merged() -> None:
    assert (
        make(company=None, source_id="1").dedupe_key != make(company=None, source_id="2").dedupe_key
    )


def test_role_hint_comes_from_the_title() -> None:
    """Excerpt postings never reach the model, so the title is all they have."""
    assert make(title="Senior Data Engineer").role_hint == "data-engineer"
    assert make(title="Software Engineer, Data Infrastructure").role_hint is None


def test_content_hash_tracks_title_and_description() -> None:
    assert make().content_hash == make(url="https://elsewhere").content_hash
    assert make().content_hash != make(description_text="y" * FULL_TEXT_MIN_CHARS).content_hash


def test_whitespace_is_stripped() -> None:
    assert make(title="  Data Analyst, NYC ").title == "Data Analyst, NYC"


@pytest.mark.parametrize(
    "field", [{"country": "usa"}, {"salary_currency": "dollars"}, {"title": ""}]
)
def test_invalid_values_are_rejected(field: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        make(**field)

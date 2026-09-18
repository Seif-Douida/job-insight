"""The extraction contract: what the model is asked for, and what is accepted back."""

from __future__ import annotations

from typing import Any, get_args

import pytest
from pydantic import ValidationError

from pipeline.extract.prompt import INSTRUCTIONS, build_prompt, response_schema
from pipeline.extract.schema import (
    Extraction,
    Requirement,
    Seniority,
    SkillKind,
    Sponsorship,
    WorkMode,
    role_slugs,
)


def extraction(**overrides: Any) -> Extraction:
    fields: dict[str, Any] = {
        "role": "data-engineer",
        "seniority": "senior",
        "work_mode": "hybrid",
        "visa_sponsorship": "not_mentioned",
        "skills": [{"name": "Python", "kind": "language", "requirement": "required"}],
    }
    return Extraction.model_validate(fields | overrides)


def test_valid_extraction_parses() -> None:
    result = extraction(years_experience_min=5)
    assert (result.role, result.seniority, result.years_experience_min) == (
        "data-engineer",
        "senior",
        5,
    )
    assert result.skills[0].name == "Python"


def test_unknown_role_becomes_other() -> None:
    """A wrong role should not throw away the skills in the same answer."""
    assert extraction(role="devops-engineer").role == "other"


def test_repeated_skills_are_collapsed() -> None:
    result = extraction(
        skills=[
            {"name": "Python", "kind": "language", "requirement": "required"},
            {"name": "python", "kind": "language", "requirement": "preferred"},
            {"name": "SQL", "kind": "language", "requirement": "required"},
        ]
    )
    assert [skill.name for skill in result.skills] == ["Python", "SQL"]


@pytest.mark.parametrize(
    "bad",
    [
        {"seniority": "very senior"},
        {"work_mode": "office"},
        {"visa_sponsorship": "maybe"},
        {"years_experience_min": -1},
        {"years_experience_min": 99},
        {"skills": [{"name": "", "kind": "language", "requirement": "required"}]},
        {"skills": [{"name": "Rust", "kind": "programming", "requirement": "required"}]},
    ],
)
def test_invalid_answers_are_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        extraction(**bad)


def test_response_schema_matches_the_model() -> None:
    """The schema sent to the API and the model validating replies must not drift apart."""
    schema = response_schema()
    properties = schema["properties"]
    assert set(properties) == set(Extraction.model_fields)
    assert set(properties["role"]["enum"]) == set(role_slugs())
    assert set(properties["seniority"]["enum"]) == set(get_args(Seniority))
    assert set(properties["work_mode"]["enum"]) == set(get_args(WorkMode))
    assert set(properties["visa_sponsorship"]["enum"]) == set(get_args(Sponsorship))
    skill = properties["skills"]["items"]["properties"]
    assert set(skill["kind"]["enum"]) == set(get_args(SkillKind))
    assert set(skill["requirement"]["enum"]) == set(get_args(Requirement))


def test_prompt_includes_context_and_truncates_long_postings() -> None:
    prompt = build_prompt(
        title="Senior Data Engineer",
        company="Acme",
        location="Berlin",
        description="x" * 50_000,
    )
    assert INSTRUCTIONS in prompt
    assert "Title: Senior Data Engineer" in prompt and "Company: Acme" in prompt
    assert len(prompt) < 20_000


def test_prompt_omits_missing_context() -> None:
    prompt = build_prompt(title="Data Analyst", company=None, location=None, description="text")
    assert "Company:" not in prompt and "Location:" not in prompt

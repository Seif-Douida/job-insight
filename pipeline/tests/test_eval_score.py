"""Scoring rules for the accuracy report."""

from __future__ import annotations

from typing import Any

import pytest

from pipeline.eval.score import normalize_skill, score

LABELS: dict[str, Any] = {
    "role": "data-engineer",
    "seniority": "senior",
    "years_experience_min": 5,
    "work_mode": "hybrid",
    "visa_sponsorship": "not_mentioned",
    "skills": ["Python", "Airflow", "dbt"],
}


def answer(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "role": "data-engineer",
        "seniority": "senior",
        "years_experience_min": 5,
        "work_mode": "hybrid",
        "visa_sponsorship": "not_mentioned",
        "skills": [{"name": "Python"}, {"name": "Airflow"}, {"name": "dbt"}],
    }
    return fields | overrides


@pytest.mark.parametrize(
    ("written", "also_written"),
    [("APIs", "api"), ("PostgreSQL", "postgresql"), ("A/B testing", "ab testing"), ("dbt", "DBT")],
)
def test_skill_names_are_compared_loosely(written: str, also_written: str) -> None:
    assert normalize_skill(written) == normalize_skill(also_written)


def test_a_perfect_answer_scores_full_marks() -> None:
    report = score([(1, LABELS, answer())])
    assert all(tally.accuracy == 1.0 for tally in report.fields.values())
    assert (report.skills.precision, report.skills.recall, report.skills.f1) == (1.0, 1.0, 1.0)
    assert report.mismatches == []


def test_wrong_fields_are_counted_and_explained() -> None:
    report = score([(1, LABELS, answer(role="ml-engineer", years_experience_min=None))])
    assert report.fields["role"].accuracy == 0.0
    assert report.fields["seniority"].accuracy == 1.0
    assert any("role: model='ml-engineer'" in line for line in report.mismatches)


def test_missed_and_invented_skills_move_recall_and_precision() -> None:
    report = score([(1, LABELS, answer(skills=[{"name": "Python"}, {"name": "Kafka"}]))])
    assert report.skills.found == 1  # Python
    assert report.skills.invented == 1  # Kafka is not in the posting
    assert report.skills.missed == 2  # Airflow, dbt
    assert (report.skills.precision, report.skills.recall) == (0.5, pytest.approx(1 / 3))


def test_a_failed_call_is_reported_not_scored() -> None:
    report = score([(1, LABELS, "ModelError: empty answer")])
    assert (report.postings, report.failures) == (1, 1)
    assert report.fields["role"].total == 0
    assert "FAILED" in report.mismatches[0]


def test_scores_average_across_postings() -> None:
    report = score([(1, LABELS, answer()), (2, LABELS, answer(role="other"))])
    assert report.fields["role"].accuracy == 0.5
    assert report.postings == 2

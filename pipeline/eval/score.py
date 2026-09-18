"""Comparing an extraction with its labels.

Single-value fields are scored by exact match. Skills are scored as a set: precision is
how much of what the model listed was really in the posting, recall how much of what the
posting names the model found. Names are compared loosely (case, punctuation and plurals
ignored) because wording varies; the canonical skill mapping in the modelling layer
handles the rest.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

FIELDS = ("role", "seniority", "years_experience_min", "work_mode", "visa_sponsorship")

_NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def normalize_skill(name: str) -> str:
    """Compare "APIs", "api" and "API." as one skill."""
    compact = _NOT_ALPHANUMERIC.sub("", name.lower())
    return compact[:-1] if compact.endswith("s") and len(compact) > 3 else compact


@dataclass
class FieldTally:
    """How often one field matched its label."""

    correct: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class SkillTally:
    """Set overlap between listed skills and labelled ones."""

    found: int = 0
    invented: int = 0
    missed: int = 0

    @property
    def precision(self) -> float:
        listed = self.found + self.invented
        return self.found / listed if listed else 0.0

    @property
    def recall(self) -> float:
        labelled = self.found + self.missed
        return self.found / labelled if labelled else 0.0

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 2 * self.precision * self.recall / total if total else 0.0


@dataclass
class Report:
    """Scores across the whole golden set, with the disagreements kept for inspection."""

    fields: dict[str, FieldTally] = field(
        default_factory=lambda: {name: FieldTally() for name in FIELDS}
    )
    skills: SkillTally = field(default_factory=SkillTally)
    postings: int = 0
    failures: int = 0
    mismatches: list[str] = field(default_factory=list)

    def add(self, posting_id: int, labels: Mapping[str, Any], answer: Mapping[str, Any]) -> None:
        """Score one extraction against its labels."""
        self.postings += 1
        for name in FIELDS:
            tally = self.fields[name]
            tally.total += 1
            if answer.get(name) == labels.get(name):
                tally.correct += 1
            else:
                self.mismatches.append(
                    f"[{posting_id}] {name}: model={answer.get(name)!r}"
                    f" labelled={labels.get(name)!r}"
                )

        labelled = {normalize_skill(name) for name in labels.get("skills", ())}
        listed = {normalize_skill(skill["name"]) for skill in answer.get("skills", ())}
        self.skills.found += len(labelled & listed)
        self.skills.invented += len(listed - labelled)
        self.skills.missed += len(labelled - listed)
        if missed := labelled - listed:
            self.mismatches.append(f"[{posting_id}] skills missed: {sorted(missed)}")
        if invented := listed - labelled:
            self.mismatches.append(f"[{posting_id}] skills not labelled: {sorted(invented)}")

    def add_failure(self, posting_id: int, error: str) -> None:
        self.postings += 1
        self.failures += 1
        self.mismatches.append(f"[{posting_id}] FAILED: {error}")

    def summary(self) -> str:
        lines = [
            f"postings: {self.postings}  failures: {self.failures}",
            f"skills:   precision {self.skills.precision:.0%}  recall {self.skills.recall:.0%}"
            f"  F1 {self.skills.f1:.0%}  (found {self.skills.found},"
            f" extra {self.skills.invented}, missed {self.skills.missed})",
        ]
        lines += [
            f"{name:<22} {tally.accuracy:.0%} ({tally.correct}/{tally.total})"
            for name, tally in self.fields.items()
        ]
        return "\n".join(lines)


def score(results: Iterable[tuple[int, Mapping[str, Any], Mapping[str, Any] | str]]) -> Report:
    """Score (posting id, labels, answer) triples; a string answer counts as a failure."""
    report = Report()
    for posting_id, labels, answer in results:
        if isinstance(answer, str):
            report.add_failure(posting_id, answer)
        else:
            report.add(posting_id, labels, answer)
    return report

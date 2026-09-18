"""What the model must return for one posting.

`Extraction` is the contract: the API is asked to follow the matching JSON Schema in
`prompt.py`, and every answer is validated here anyway. Validation is what counts, since
a model can return well-formed JSON that is still wrong (an unknown role, a skill listed
twice, a negative number of years).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipeline.taxonomy import load_roles

Requirement = Literal["required", "preferred", "unclear"]
SkillKind = Literal["language", "framework", "tool", "platform", "cloud", "concept"]
"""No "soft" kind: generic qualities are not skills a market report should count."""
Seniority = Literal["intern", "junior", "mid", "senior", "lead", "principal", "unclear"]
WorkMode = Literal["remote", "hybrid", "onsite", "unclear"]
Sponsorship = Literal["offered", "explicitly_not", "not_mentioned"]

OTHER_ROLE = "other"
MAX_YEARS = 40


def role_slugs() -> tuple[str, ...]:
    """Curated role slugs the model may answer with, plus `other`."""
    return tuple(role.slug for role in load_roles()) + (OTHER_ROLE,)


class ExtractedSkill(BaseModel):
    """One skill, tool or technology a posting names."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    kind: SkillKind
    requirement: Requirement


class Extraction(BaseModel):
    """Everything read out of one posting."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    role: str
    seniority: Seniority
    years_experience_min: int | None = Field(default=None, ge=0, le=MAX_YEARS)
    work_mode: WorkMode
    visa_sponsorship: Sponsorship
    skills: tuple[ExtractedSkill, ...] = ()

    @field_validator("role", mode="before")
    @classmethod
    def _known_role(cls, value: Any) -> str:
        """An unrecognized role becomes `other` rather than failing the whole extraction."""
        return value if value in role_slugs() else OTHER_ROLE

    @field_validator("skills", mode="after")
    @classmethod
    def _unique_skills(cls, skills: tuple[ExtractedSkill, ...]) -> tuple[ExtractedSkill, ...]:
        """Models sometimes repeat a skill; keep the first mention of each name."""
        seen: dict[str, ExtractedSkill] = {}
        for skill in skills:
            seen.setdefault(skill.name.casefold(), skill)
        return tuple(seen.values())

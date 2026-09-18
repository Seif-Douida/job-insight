"""Companies whose public job boards are read directly (see companies.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from pipeline.taxonomy._files import read_yaml

BOARD_TYPES = ("greenhouse", "lever", "ashby", "smartrecruiters")


@dataclass(frozen=True)
class Company:
    """A company and the public job board it publishes postings on."""

    name: str
    ats: str
    board: str


@cache
def load_companies() -> tuple[Company, ...]:
    """Every curated company, validated: known board types, no board listed twice."""
    companies = tuple(Company(**entry) for entry in read_yaml("companies.yaml")["companies"])
    for company in companies:
        if company.ats not in BOARD_TYPES:
            raise ValueError(f"{company.name}: unknown ats {company.ats!r}")
    boards = [(company.ats, company.board) for company in companies]
    if len(boards) != len(set(boards)):
        raise ValueError("companies.yaml lists the same board more than once")
    return companies

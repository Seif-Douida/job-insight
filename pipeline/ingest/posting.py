"""The normalized posting that every source client produces."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pipeline.ingest.text import normalize_company
from pipeline.taxonomy import match_role, normalize_title, region_for_country

Source = Literal["greenhouse", "lever", "ashby", "smartrecruiters", "adzuna", "jsearch"]
TextQuality = Literal["full", "excerpt"]

AGGREGATOR_SOURCES = frozenset({"adzuna", "jsearch"})
EXCERPT_ONLY_SOURCES = frozenset({"adzuna"})

FULL_TEXT_MIN_CHARS = 1000
"""Shorter descriptions count as excerpts, whatever the source. Aggregators often return
a ~500-character snippet of a longer posting."""


class RawPosting(BaseModel):
    """One job posting from one source, normalized and validated at construction."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    source: Source
    source_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str | None = None
    location_raw: str | None = None
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    description_text: str = ""
    posted_at: datetime | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    salary_is_predicted: bool = False

    @property
    def region(self) -> str:
        return region_for_country(self.country)

    @property
    def text_quality(self) -> TextQuality:
        if self.source in EXCERPT_ONLY_SOURCES or len(self.description_text) < FULL_TEXT_MIN_CHARS:
            return "excerpt"
        return "full"

    @property
    def role_hint(self) -> str | None:
        """Role the title matches, or None when only the description could tell.

        Excerpt postings never reach the model, so this is the only role they get.
        """
        return match_role(self.title)

    @property
    def content_hash(self) -> str:
        """Changes when the title or description changes; drives updates on re-ingest."""
        return _sha256(f"{self.title}\n{self.description_text}")

    @property
    def dedupe_key(self) -> str:
        """Same company, title and country is taken to be the same job, whatever the source."""
        if not self.company:
            return _sha256(f"{self.source}:{self.source_id}")  # unknown employer: never merged
        parts = (normalize_company(self.company), normalize_title(self.title).strip(), self.country)
        return _sha256("|".join(part or "" for part in parts))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

"""The extraction prompt and the JSON Schema the model is held to.

Change PROMPT_VERSION whenever the wording or schema changes: extractions are stored per
(posting, model, prompt version, content hash), so a new version re-extracts rather than
silently mixing results from different instructions.
"""

from __future__ import annotations

from typing import Any

from pipeline.extract.schema import role_slugs

PROMPT_VERSION = "v2"

MAX_POSTING_CHARS = 12000
"""Longer postings are cut here. Requirements come early; the tail is usually benefits
and legal boilerplate."""

ROLE_GUIDE = """- data-engineer: builds pipelines, warehouses, lakehouses and data platforms
- analytics-engineer: models warehouse data for analysis (dbt, semantic layers)
- data-analyst: analyses data and builds reports, dashboards and product metrics
- data-scientist: statistics, experiments and modelling to answer business questions
- ml-engineer: trains, fine-tunes, evaluates and ships machine learning models; also
  research scientists whose models go to production
- mlops-engineer: infrastructure, deployment, serving and monitoring for models
- ai-engineer: builds products on top of existing models: LLM APIs, prompts, agents,
  retrieval-augmented generation, model integrations
- other: everything else, including general software engineering, consulting, pre-sales
  and management roles, even when the product they work on involves AI"""

SKILL_RULES = """- Name skills as they are commonly written, one concept per entry:
  "PostgreSQL" not "postgres db", "Airflow" not "Apache Airflow", "AWS" not "Amazon Web
  Services", "Weights & Biases" not "W&B". Split combinations: "ETL/ELT" becomes "ETL"
  and "ELT"; "AI/ML" becomes "AI" and "machine learning". No version numbers.
- Take skills from the responsibilities as well as the requirements.
- Never list: degrees, fields of study ("PhD", "Computer Science"), years of experience,
  job titles, company or product names that are not technologies, or generic qualities
  ("communication", "teamwork", "problem solving", "attention to detail")."""

INSTRUCTIONS = f"""You read one job posting and return structured facts about it.

Rules:
- Only record what the posting states. Never infer a skill it does not name.
- skills: every technology, language, framework, tool, platform, cloud service and named
  technical practice in the posting.
{SKILL_RULES}
- requirement: "required" when the posting demands it (must have, required, X+ years of),
  "preferred" when it is optional (nice to have, bonus, plus), "unclear" otherwise.
- role: which role the posting is for, judged by the responsibilities, not the title alone:
{ROLE_GUIDE}
- seniority: "staff" and "principal" both count as principal; managers, directors and
  heads count as lead. Use "unclear" when the posting names no level and no years of
  experience.
- years_experience_min: the smallest number of years of experience required, else null.
- work_mode: only when the posting says so ("remote", "hybrid", "on-site", "in office
  X days a week"). An office address on its own is not a work mode: answer "unclear".
- visa_sponsorship: "offered" if the posting offers sponsorship or relocation support,
  "explicitly_not" if it rules it out or demands existing work authorization,
  "not_mentioned" otherwise.

Answer with JSON only."""


def build_prompt(*, title: str, company: str | None, location: str | None, description: str) -> str:
    """The full prompt for one posting: instructions, then its text."""
    header = "\n".join(
        line
        for line in (
            f"Title: {title}",
            f"Company: {company}" if company else "",
            f"Location: {location}" if location else "",
        )
        if line
    )
    return f"{INSTRUCTIONS}\n\n--- JOB POSTING ---\n{header}\n\n{description[:MAX_POSTING_CHARS]}"


def response_schema() -> dict[str, Any]:
    """JSON Schema the model must follow; role values come from the taxonomy."""
    return {
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": list(role_slugs())},
            "seniority": {
                "type": "string",
                "enum": ["intern", "junior", "mid", "senior", "lead", "principal", "unclear"],
            },
            "years_experience_min": {"type": ["integer", "null"]},
            "work_mode": {"type": "string", "enum": ["remote", "hybrid", "onsite", "unclear"]},
            "visa_sponsorship": {
                "type": "string",
                "enum": ["offered", "explicitly_not", "not_mentioned"],
            },
            "skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": [
                                "language",
                                "framework",
                                "tool",
                                "platform",
                                "cloud",
                                "concept",
                            ],
                        },
                        "requirement": {
                            "type": "string",
                            "enum": ["required", "preferred", "unclear"],
                        },
                    },
                    "required": ["name", "kind", "requirement"],
                },
            },
        },
        "required": ["role", "seniority", "work_mode", "visa_sponsorship", "skills"],
    }

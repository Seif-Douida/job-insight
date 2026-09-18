"""Generate the first draft of the skill alias seed, then maintain it by hand.

    python -m pipeline.taxonomy.build_skill_aliases

Two things fragment a skill count: casing ("Python" / "python") and wording ("LLM" /
"large language models"). Casing is not worth a file - the join is case-insensitive, and
the canonical spelling here is simply the one employers used most. Wording is a judgement
call, so those groups are written out in SYNONYMS below and reviewed by a person.

Rewriting the file keeps every alias already in it: names are added as the corpus grows,
and a decision once made is not silently reversed by a later run.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pipeline.db import connect

SEED_PATH = Path(__file__).resolve().parents[1] / "dbt" / "seeds" / "skill_aliases.csv"

TOP_NAMES = 400
"""How far down the frequency list to go. The top 400 names are about two thirds of all
mentions; below that is mostly one-off phrasing that no percentage should rest on."""

SYNONYMS: dict[str, tuple[str, ...]] = {
    # canonical: other ways employers write it (lowercase, no need to list casings)
    "LLM": ("llms", "large language models", "large language model"),
    "AI": ("artificial intelligence",),
    "Generative AI": ("genai", "gen ai", "generative ai"),
    "RAG": ("retrieval-augmented generation", "retrieval augmented generation"),
    "AI agents": ("agents", "agentic ai", "agentic systems", "agentic workflows"),
    "Machine learning": ("ml",),
    "Deep learning": ("dl",),
    "NLP": ("natural language processing",),
    "Computer vision": ("cv",),
    "Go": ("golang",),
    "PostgreSQL": ("postgres", "psql"),
    "Kubernetes": ("k8s",),
    "AWS": ("amazon web services",),
    "GCP": ("google cloud", "google cloud platform"),
    "Azure": ("microsoft azure",),
    "Spark": ("apache spark",),
    "Kafka": ("apache kafka",),
    "Airflow": ("apache airflow",),
    "Flink": ("apache flink",),
    "Iceberg": ("apache iceberg",),
    "scikit-learn": ("sklearn", "scikit learn"),
    "A/B testing": ("ab testing", "a/b tests", "a/b test", "split testing"),
    "CI/CD": ("cicd", "continuous integration", "continuous integration/continuous deployment"),
    "Data modeling": ("data modelling", "dimensional modeling"),
    "Semantic layer": ("semantic layers",),
    "Recommender systems": ("recommendation systems", "recommendation engines"),
    "Vector databases": ("vector database", "vector stores", "vector store"),
    "Fine-tuning": ("finetuning", "fine tuning"),
    "Prompt engineering": ("prompting",),
    "Model evaluation": ("evals", "model evals"),
    "APIs": ("api", "rest apis", "rest api", "restful apis"),
    "Data pipelines": ("data pipeline", "etl pipelines"),
    "Statistical modeling": ("statistical modelling",),
    "Power BI": ("powerbi",),
    "Node.js": ("nodejs", "node"),
    "TypeScript": ("ts",),
    "JavaScript": ("js",),
    "Distributed systems": ("distributed computing",),
    "Time series forecasting": ("time series", "time-series forecasting"),
    "Experimentation": ("experiment design", "experimental design"),
    "Business intelligence": ("bi",),
    "Data warehouse": ("data warehousing", "data warehouses"),
    "Data lakehouse": ("lakehouse",),
    "Feature engineering": ("feature extraction",),
    "Model serving": ("model deployment", "model inference"),
    "Infrastructure as code": ("iac",),
    "High-performance computing": ("hpc",),
    "Reinforcement learning": ("rl",),
    "RLHF": ("reinforcement learning from human feedback",),
    "Transformers": ("transformer models", "transformer architectures"),
    "Multi-agent systems": ("multi-agent orchestration", "multi agent systems"),
    "Data quality": ("data validation",),
    "Data governance": ("governance",),
    "Version control": ("source control",),
}


def existing_rows() -> dict[str, tuple[str, str]]:
    """Aliases already decided, keyed by alias."""
    if not SEED_PATH.exists():
        return {}
    with SEED_PATH.open(encoding="utf-8", newline="") as handle:
        return {
            row["alias"]: (row["canonical_skill"], row["kind"]) for row in csv.DictReader(handle)
        }


def main() -> None:
    with connect() as conn:
        rows = conn.execute(
            """
            select lower(skill_raw) as alias, count(*) as mentions,
                   mode() within group (order by skill_raw) as spelling,
                   mode() within group (order by kind) as kind
            from analytics.stg_skill_mentions
            group by 1 order by 2 desc limit %s
            """,
            (TOP_NAMES,),
        ).fetchall()

    canonical_of = {alias: name for name, aliases in SYNONYMS.items() for alias in aliases}
    canonical_of.update({name.lower(): name for name in SYNONYMS})

    aliases = existing_rows()
    kinds = {alias: kind for alias, _, _, kind in rows}
    added = 0
    for alias, _mentions, spelling, kind in rows:
        if alias in aliases:
            continue
        canonical = canonical_of.get(alias, spelling)
        aliases[alias] = (canonical, kinds.get(canonical.lower(), kind))
        added += 1

    SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SEED_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["alias", "canonical_skill", "kind"])
        for alias in sorted(aliases):
            writer.writerow([alias, *aliases[alias]])

    canonical_names = {canonical for canonical, _ in aliases.values()}
    print(f"{len(aliases)} aliases -> {len(canonical_names)} canonical skills ({added} new)")


if __name__ == "__main__":
    main()

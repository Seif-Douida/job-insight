# Job Insight

What do companies in a given region actually want from a given role?

This project collects job postings from public sources, extracts the skills, tools and
requirements from each one with an LLM, and aggregates the results into evidence-backed
answers: *"78% of Data Engineer postings in the EU ask for Python, 41% ask for dbt."*

- **Roles:** Data Engineer, Analytics Engineer, Data Analyst, AI Engineer, ML Engineer, MLOps Engineer, Data Scientist
- **Regions:** USA, UK, EU, Gulf (each drillable to country level)
- **Insights:** skill demand %, required vs. nice-to-have, seniority and years of experience,
  salary ranges, visa sponsorship, remote share, skill co-occurrence, and trends over time

## Stack

| Layer | Tool |
| ----- | ---- |
| Ingestion | Public ATS boards (Greenhouse/Lever/Ashby), Adzuna, JSearch |
| Orchestration | Apache Airflow |
| Extraction | Gemma 4 via Gemini API (Ollama as local backend) |
| Modeling | dbt on Postgres |
| Storage | Neon Postgres |
| Dashboard | Next.js on Vercel |

Every number is published with its sample size; cohorts below 25 postings are marked
low-confidence. See [docs/methodology.md](docs/methodology.md) for sources and known biases.

## Status

Phase 1 of 6 (foundation) complete; phase 2 (ingestion) next. See [docs/PROGRESS.md](docs/PROGRESS.md) for the running log and
[docs/design.md](docs/design.md) for the full design.

## Getting started

See [CLAUDE.md](CLAUDE.md) for setup and commands.

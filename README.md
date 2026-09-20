# Job Insight

What do companies in a given region actually want from a given role?

This project collects job postings from public sources, extracts the skills, tools and
requirements from each one with an LLM, and aggregates the results into evidence-backed
answers: *"70% of Data Engineer postings in the US ask for Python, 36% ask for dbt."*

- **Roles:** Data Engineer, Analytics Engineer, Data Analyst, AI Engineer, ML Engineer, MLOps Engineer, Data Scientist
- **Regions:** US, UK, EU, Gulf (each drillable to country level)
- **Insights:** skill demand %, required vs. nice-to-have, seniority and years of experience,
  salary ranges, visa sponsorship, remote share

Every number is published with its sample size; cohorts below 25 postings are marked
low-confidence rather than hidden. See [docs/methodology.md](docs/methodology.md) for
sources and known biases, and [docs/lessons.md](docs/lessons.md) for what went wrong along
the way and what each mistake taught.

## Stack

| Layer | Tool |
| ----- | ---- |
| Ingestion | ATS boards (Greenhouse, Lever, Ashby, SmartRecruiters, Workday), Adzuna, JSearch |
| Orchestration | Apache Airflow 3 |
| Extraction | Gemma 4 via Gemini API (Ollama as local backend) |
| Modeling | dbt on Postgres |
| Storage | Neon Postgres |
| Dashboard | Next.js on Vercel |

Running cost is zero: every service is a free tier.

## Status

Phases 1–4 of 6 are complete and phase 5 is in progress. The pipeline runs unattended —
ingest at 03:00, extraction at 06:00, `dbt build` at 08:00 — collecting from 185 company
job boards, Adzuna and JSearch into Neon, and the dashboard reads the marts it produces.

| | |
| --- | --- |
| Postings collected | 3,052 with full text |
| Analysed in the current window | 1,711 across 270 companies |
| Company job boards | 185 across five ATS platforms |
| Publishable cohorts | 18 of 28 role-and-region pairs |
| Tests | 202 pytest, 25 dbt models and data tests |

Still to come: the remaining dashboard views, then deployment to an Oracle Cloud VM and
Vercel. See [docs/PROGRESS.md](docs/PROGRESS.md) for the running log and
[docs/design.md](docs/design.md) for the full design.

## Running it

See [CLAUDE.md](CLAUDE.md) for setup and the full command list. In short:

```bash
cp infra/.env.example .env          # then fill in the credentials
python -m pip install -e ".[dev]"
python -m pipeline.db.migrate
docker compose -f infra/docker-compose.yml up -d    # Airflow at localhost:8080

cd web && npm install && npm run dev                # dashboard at localhost:3000
```

# Progress log

Running record of what exists, what was verified, and what comes next.
Newest entry first. Update before every phase-closing commit.

## Phases

| # | Phase | Status |
| --- | ----- | ------ |
| 1 | Foundation — repo, config, schema, Airflow up | done 2026-09-17 |
| 2 | Ingestion — ATS boards, Adzuna, JSearch, dedupe | next |
| 3 | Extraction — LLM backends, quota governor, eval | not started |
| 4 | Modeling — dbt staging → marts, taxonomy | not started |
| 5 | Dashboard — Next.js pages and API routes | not started |
| 6 | Ops — Oracle VM deploy, schedules, Vercel | not started |

---

## 2026-09-17 — Phase 1: Foundation (done)

### Built

- Repo initialized, remote `origin` → <https://github.com/Seif-Douida/job-insight.git>
- `docs/design.md` — approved design; `CLAUDE.md` — setup, commands, conventions
- `infra/sql/001_raw_schema.sql` — `raw.postings`, `raw.extractions`, `raw.quota_usage`
- `pipeline/taxonomy/` — 7 curated roles with title matcher; US / UK / EU / Gulf → 23 countries
- `pipeline/db/` — connection helper and idempotent `migrate` command
- `infra/docker-compose.yml` — Airflow 3.3.1 standalone + metadata Postgres 16
- `pipeline/dags/db_healthcheck.py` — smoke-test DAG for taxonomy and database access
- All credentials in `.env` (Neon, Gemini, Adzuna, RapidAPI)

### Verified

```text
$ pytest -q
22 passed in 0.13s

$ ruff check pipeline && black --check pipeline
All checks passed!
7 files would be left unchanged.

$ python -m pipeline.db.migrate        # run twice: idempotent
applied 001_raw_schema.sql
raw tables: ['extractions', 'postings', 'quota_usage']   # Neon, PostgreSQL 18.6

$ airflow dags list
db_healthcheck | /opt/airflow/repo/pipeline/dags/db_healthcheck.py | airflow | True

$ airflow dags test db_healthcheck     # inside the container, against Neon
check_taxonomy  → {'roles': 7, 'countries': 23}          state=success
check_database  → {'postings': 0, 'extractions': 0}      state=success
DagRun Finished: state=success, run_duration=6.25s
```

### Deferred (deliberately)

- Airflow runs as `standalone` (one container) rather than split scheduler/api-server
  services. Simplest thing that works locally; revisit only if phase 6 needs it.
- dbt and Cosmos arrive in phase 4, not now.
- `companies.yaml` (the ATS coverage list) is phase 2 work.

### Notes

- The Airflow `admin` password is regenerated whenever the container is recreated. Read it
  with `docker compose -f infra/docker-compose.yml logs airflow | grep "Password for user"`.
- Editing `.env` requires `docker compose -f infra/docker-compose.yml up -d --force-recreate airflow`
  for the container to see the change.

### Next

Phase 2 — ingestion. Order: shared `RawPosting` model + normalization and dedupe →
Greenhouse / Lever / Ashby clients with a first `companies.yaml` → Adzuna → JSearch (Gulf).
Each client tested against recorded API fixtures before touching live endpoints.

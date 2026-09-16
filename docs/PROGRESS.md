# Progress log

Running record of what exists, what was verified, and what comes next.
Newest entry first. Update before every phase-closing commit.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | Foundation — repo, config, schema, Airflow up | in progress |
| 2 | Ingestion — ATS boards, Adzuna, JSearch, dedupe | not started |
| 3 | Extraction — LLM backends, quota governor, eval | not started |
| 4 | Modeling — dbt staging → marts, taxonomy | not started |
| 5 | Dashboard — Next.js pages and API routes | not started |
| 6 | Ops — Oracle VM deploy, schedules, Vercel | not started |

---

## 2026-09-16 — Phase 1: Foundation (in progress)

### Built

- Repo initialized, remote `origin` → https://github.com/Seif-Douida/job-insight.git
- `docs/design.md` — approved design; `CLAUDE.md` — setup, commands, conventions
- `infra/sql/001_raw_schema.sql` — `raw.postings`, `raw.extractions`, `raw.quota_usage`
- `pipeline/taxonomy/roles.yaml` — 7 curated roles with title-matching patterns
- `pipeline/taxonomy/regions.yaml` — US / UK / EU / Gulf → country codes

### Verified

_Pending: `docker compose up`, `airflow dags list`, schema applied to Neon._

### Deferred (deliberately)

- Airflow runs as `standalone` (one container) rather than split scheduler/api-server
  services. Simplest thing that works locally; revisit only if phase 6 needs it.
- dbt and Cosmos arrive in phase 4, not now.
- `companies.yaml` (the ATS coverage list) is phase 2 work.

### Blocked on credentials

Needed in `.env` before the pipeline can touch real data:

| Variable | Where to get it |
|----------|-----------------|
| `DATABASE_URL` | Neon project connection string (free tier) |
| `GEMINI_API_KEY` | Google AI Studio |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | developer.adzuna.com (free, 1,000 calls/month) |
| `RAPIDAPI_KEY` | RapidAPI, for JSearch (Gulf coverage, phase 2) |

### Next

Finish phase 1 verification, then phase 2 ingestion starting with the ATS clients
(they need no credentials, so work can proceed while the keys are gathered).

# Job Market Insights — Design & Implementation Plan

## Context

Nothing exists yet; `c:\Users\seif\Desktop\Projects\market_insights` is empty and not a git repo.

The goal is a system that answers **"What do companies in [Region] want from a [Role]?"** with evidence: which skills, frameworks and tools appear in job postings, at what percentage, for a curated set of data/AI roles across the USA, UK, EU and Gulf.

It is a **portfolio project**: zero running cost, legal and stable data sources, and an architecture that mirrors what Data/AI Engineer postings actually ask for (Airflow, dbt, Postgres, LLM extraction, a deployed dashboard). Accuracy and honest statistics matter more than raw coverage — the project is itself a demonstration of data quality practice.

## Decisions already made

| Area | Decision |
| --- | --- |
| Sources | Public ATS boards (Greenhouse/Lever/Ashby) as full-text backbone; Adzuna for breadth + salary; JSearch for Gulf gaps |
| Extraction | LLM → structured JSON, then alias→canonical skill taxonomy |
| Default model | `gemma-4-26b-a4b-it` via Gemini API (30 RPM / 14,400 RPD free); `gemma-4-31b-it` benchmarked; Ollama local secondary; Gemini Flash emergency fallback only (20 RPD) |
| Orchestration | Airflow (dbt models run as Airflow tasks via Cosmos) |
| Storage | Single Neon Postgres (free tier) — raw, staging and marts; raw full text archived as gzipped JSONL on the server |
| Host | Oracle Cloud Always Free ARM VM, Docker Compose |
| Frontend | Next.js (App Router) on Vercel, reading Neon directly through route handlers |
| Roles | 7 curated: data-engineer, analytics-engineer, data-analyst, ai-engineer, ml-engineer, mlops-engineer, data-scientist |
| Insights | Skill %, required vs. nice-to-have, seniority/years, salary, visa sponsorship, trends over time, skill co-occurrence, remote share |

## Working agreements

These hold for every phase and override any temptation to move faster.

- **Clean code.** Small modules with one purpose each, explicit names, type hints on public functions, formatted and linted (ruff + black; ESLint/Prettier on the web app). One source client per file; no god-module.
- **Simplest thing that works.** No component enters the stack unless a phase needs it. Concretely ruled out unless a real need appears: message queues, Redis/caching layers, auth and user accounts, a separate API service (Next.js route handlers are the API), request batching in extraction, and any second warehouse engine. Plain SQL and dbt beat clever Python.
- **Tests and evaluation are acceptance criteria, not follow-up work.** Every phase ships its tests with it: unit tests against recorded source fixtures, dbt tests on every mart, and the golden-set eval for anything the LLM produces. A phase is closed only when its verification command has been run and its output recorded.
- **Document as we go.** `docs/PROGRESS.md` is the running log: what was built, what was verified (with the actual command output), what is deliberately deferred, and what is next. Updated at the end of each phase, before the commit. `CLAUDE.md` at the repo root holds setup, commands and conventions so any later session can pick up cold.
- **Git from the first commit.** `git init` in phase 1, remote `origin` set to `https://github.com/Seif-Douida/job-insight.git`, one commit per meaningful step, and a push after each phase. Secrets live only in `.env`, with `.env.example` checked in.

## Architecture

```text
Sources ──► raw.postings ──► extraction (LLM) ──► raw.extractions
   │                                                     │
   │  ATS boards (full text, primary)                    ▼
   │  Adzuna (excerpt + salary)                    dbt: staging → int → marts
   │  JSearch (full text, Gulf)                          │
   └─────────────── Airflow on Oracle VM ────────────────┘
                                                         ▼
                                        Neon Postgres ──► Next.js on Vercel
```

**Data quality rule that shapes everything:** every posting carries `text_quality` (`full` | `excerpt`). Percentages for context-dependent fields (required vs. nice-to-have, seniority, sponsorship) are computed **only over `full`** postings. Excerpt postings contribute to volume, salary and company/region coverage. The two are never mixed inside one percentage.

## Repository layout

```text
market_insights/
├── pipeline/
│   ├── dags/                 # ingest_ats.py, ingest_adzuna.py, ingest_jsearch.py, extract.py, transform.py
│   ├── ingest/               # one client per source + shared normalizer, dedupe
│   ├── extract/              # llm/ (base.py, gemini.py, ollama.py), schema.py, prompts/, quota.py
│   ├── taxonomy/             # skills.yaml, roles.yaml, regions.yaml, companies.yaml
│   ├── eval/                 # golden_set.jsonl, run_eval.py
│   ├── dbt/                  # models/staging, models/intermediate, models/marts, seeds/skill_aliases.csv
│   └── tests/
├── web/                      # Next.js App Router app
├── infra/                    # docker-compose.yml, server bootstrap, .env.example
├── docs/                     # PROGRESS.md (running log), methodology.md, this design
└── CLAUDE.md                 # setup, commands, conventions
```

## Components

### 1. Ingestion

Each client returns a common `RawPosting`, upserted on `(source, source_id)` so re-runs are idempotent.

`raw.postings`: `id, source, source_id, url, title, company, location_raw, country, region, description_text, text_quality, posted_at, salary_min, salary_max, salary_currency, salary_is_predicted, content_hash, dedupe_key, duplicate_of, ingested_at`

- **ATS boards** — no key, no practical rate limit, full descriptions:
  `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`, `api.lever.co/v0/postings/{company}?mode=json`, `api.ashbyhq.com/posting-api/job-board/{name}`. Driven by `companies.yaml` (company → ATS + token + HQ region). This list is the coverage lever; Gulf entries need deliberate curation.
- **Adzuna** — `/v1/api/jobs/{country}/search/{page}`, `results_per_page=50`, `max_days_old` on a daily window. Budget: 1,000 calls/month total, allocated per country in config. Excerpt text only. Always link out via `redirect_url`; never republish descriptions.
- **JSearch** — ~200 requests/month, reserved for Gulf queries (AE, SA, QA, KW, BH, OM). Full text.
- **Dedupe** — `dedupe_key = hash(normalize(company) + normalize(title) + country)`; on collision keep the richest record as canonical (ATS > JSearch > Adzuna) and point the rest at it via `duplicate_of`. Aggregates count canonical rows only.
- **Region mapping** — country → region in `regions.yaml`; country retained so the UI can drill from EU into Germany.

### 2. Extraction

- **Role classification first, cheaply:** title regex/alias pass from `roles.yaml`; only ambiguous titles go to the LLM. Postings that match no curated role are stored as `other` and excluded from aggregates.
- **LLM interface:** `extract/llm/base.py` defines `extract(posting) -> ExtractionResult`; backends `gemini.py` (Gemma 4 and Flash) and `ollama.py` share prompts, so model comparison is a config change.
- **Output schema** (Pydantic, one posting per request):
  `skills[{name, kind: language|framework|tool|platform|cloud|concept|soft, requirement: required|preferred|unclear}]`, `seniority`, `years_experience_min/max`, `work_mode`, `visa_sponsorship: offered|explicitly_not|not_mentioned`, `education_required`, `role_guess`.
- **First task of this phase (spike):** check whether `responseJsonSchema` works for `gemma-4-*` on the Gemini API. If yes, use it; if not, schema-in-prompt plus Pydantic validation and a single repair retry. Either way validation is authoritative.
- **Quota governor** (`extract/quota.py`): token bucket at 25 RPM with a 13,000/day cap (buffer under 30/14,400), counters persisted in Postgres so restarts don't double-spend. On exhaustion the task exits cleanly and the backlog carries to the next run. Optional Ollama overflow backend.
- **Storage:** `raw.extractions (posting_id, model, prompt_version, payload jsonb, status, tokens, latency_ms, extracted_at)`. Keeping raw JSON means taxonomy changes never require re-calling the LLM.
- **Re-extraction:** `(model, prompt_version)` in the key lets a better model re-process the archive later without losing history.
- **Text retention:** after successful extraction, `description_text` is trimmed to 1,000 chars in Postgres (Neon free tier is 0.5 GB) and the full text is appended to a gzipped JSONL archive on the server disk.

### 3. Modeling (dbt)

- `stg_postings`, `stg_extractions` (skills array flattened to one row per mention).
- `int_skill_mentions` — joins mention text to canonical skill via seed `skill_aliases.csv` (`alias, canonical_skill, kind`). Unmapped names land in `unmapped_skills` with counts; a weekly report surfaces the top ones for review. This loop is what keeps "Postgres/PostgreSQL/psql" from fragmenting the percentages.
- `int_postings_enriched` — role, region, country, seniority, work_mode, sponsorship, salary, text_quality.
- Marts: `mart_role_region_summary`, `mart_skill_demand` (role × region × skill: `n_with_skill, n_total, pct, pct_required`), `mart_skill_by_seniority`, `mart_salary` (p25/p50/p75 per role × region × seniority × currency, stated salaries only), `mart_sponsorship`, `mart_skill_trend` (monthly, keyed on `posted_at` so a missed collection day leaves no gap), `mart_skill_cooccurrence` (top ~150 skills per cohort, support + lift).
- **Statistical guardrails:** every mart row carries `n`; cohorts with `n < 25` are flagged `low_confidence` and hidden by default in the UI. Salary percentiles need `n >= 10` stated salaries.
- dbt tests: not_null/unique/relationships, plus custom tests that `pct` ∈ [0,1], `n_with_skill <= n_total`, and no published cohort is missing its `n`.

### 4. Dashboard (Next.js on Vercel)

Route handlers query Neon with a read-only role; marts are small, so responses cache well.

- `/` — pick role + region.
- `/role/[role]/[region]` — ranked skill bars with % and required-share, seniority toggle, salary block, sponsorship block, remote share, top hiring companies, and a visible "based on N postings, [date range]" line.
- `/compare/regions?role=…&a=us&b=eu` — sorted by largest gap.
- `/compare/roles?region=…&a=…&b=…` — shared core vs. distinctive skills.
- `/skill/[skill]` — role × region heatmap, monthly trend, related skills from co-occurrence.
- `/methodology` — sources, sample sizes, known biases (ATS list skews to tech companies, Gulf coverage thinner, excerpt vs. full text). Essential for credibility.

## Verification

Each phase has a concrete check; nothing is "done" without it.

1. **Foundation** — `docker compose up` brings up Airflow + local Postgres; `airflow dags list` shows the DAGs; `psql $NEON_URL -c '\dt raw.*'` shows the schema.
2. **Ingestion** — run each ingest DAG; verify counts by source/region in SQL, re-run and confirm row count is unchanged (idempotency), and confirm dedupe by checking a company posted on two sources.
3. **Extraction** — `python -m eval.run_eval` against the 50-posting golden set reports precision/recall for skills, role and seniority per model (26b vs. 31b vs. Ollama); extract 1,000 postings and confirm the quota governor never exceeds 25 RPM / 13k per day.
4. **Modeling** — `dbt build` passes all tests; spot-check one cohort (e.g. Data Engineer / USA) by reading 20 postings by hand and comparing the top 10 skills.
5. **Dashboard** — `npm run dev`, load each page against real data, and confirm a page's numbers match the same query run directly in SQL; Playwright smoke test per route.
6. **Ops** — pipeline deployed to the Oracle VM on schedule (daily ingest + extract, weekly marts), Vercel deployment live, a failed task visibly alerts.

CI (GitHub Actions): ruff + pytest on the pipeline, `dbt build` against an ephemeral Postgres service, `next build` on the web app.

## Implementation phases

1. Foundation — git init, repo skeleton, `CLAUDE.md`, `docs/PROGRESS.md`, Docker Compose (Airflow 3 + Postgres), Neon project, schemas, `roles/regions/companies/skills` config.
2. Ingestion — ATS clients → Adzuna → JSearch, with normalization and dedupe.
3. Extraction — schema spike, LLM backends, quota governor, golden set + eval harness.
4. Modeling — dbt staging → marts, alias taxonomy, unmapped-skill review loop, guardrails.
5. Dashboard — pages, API routes, methodology page.
6. Ops — Oracle VM deploy, schedules, Vercel, alerting.

Phases 1–4 each end in something inspectable in SQL; the dashboard only comes after the numbers are trustworthy.

Every phase closes the same way: its tests pass, its verification command from the section above has been run, `docs/PROGRESS.md` records the result and what remains, and the work is committed (and pushed once the remote exists). No phase starts before the previous one is closed that way.

## Risks

- **Oracle ARM capacity** is regionally scarce; fallback is a €5/mo VPS or running locally on a schedule.
- **Gemma structured output** may lack `responseJsonSchema` — mitigated by validation + repair retry (spike in phase 3).
- **ATS company list is the coverage bottleneck**, especially for the Gulf; treat `companies.yaml` as a living asset, supplemented by JSearch.
- **Free-tier limits drift**; all quotas live in config, not code.
- **Trends start empty** — no historical backfill exists, so trend views stay hidden until ~8 weeks of data accumulate.
- **Adzuna terms** restrict commercial use; this stays non-commercial, links out, and never republishes descriptions.

Running cost: $0 (Oracle Free + Neon Free + Vercel Hobby + Gemini free tier).

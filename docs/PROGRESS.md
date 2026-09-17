# Progress log

Running record of what exists, what was verified, and what comes next.
Newest entry first. Update before every phase-closing commit.

## Phases

| # | Phase | Status |
| --- | ----- | ------ |
| 1 | Foundation — repo, config, schema, Airflow up | done 2026-09-17 |
| 2 | Ingestion — ATS boards, Adzuna, JSearch, dedupe | done 2026-09-17 |
| 3 | Extraction — LLM backends, quota governor, eval | next |
| 4 | Modeling — dbt staging → marts, taxonomy | not started |
| 5 | Dashboard — Next.js pages and API routes | not started |
| 6 | Ops — Oracle VM deploy, schedules, Vercel | not started |

---

## 2026-09-17 — Phase 2: Ingestion (done)

### Built

- `pipeline/ingest/` — one client per source (Greenhouse, Lever, Ashby, Adzuna, JSearch),
  each parsed into a validated `RawPosting`; `store.py` upserts and links duplicates;
  `run.py` holds the retryable units of work the DAGs call
- `pipeline/taxonomy/` split into roles, regions and companies, with `resolve_country()`
  for free-text locations and `companies.yaml` listing 127 verified company boards
- `pipeline/ingest/probe_boards.py` — finds which ATS a company uses, to grow that list
- DAGs `ingest_ats` (daily), `ingest_adzuna` and `ingest_jsearch` (weekly), each mapped
  per unit of work so one failure retries alone
- `.github/workflows/ci.yml` — ruff, black and pytest against a Postgres service
- Recorded real API responses as fixtures in `pipeline/tests/fixtures/`

### Verified

```text
$ pytest -q
111 passed

GitHub Actions run for 266367c: success

Airflow runs (triggered 2026-09-17):
  ingest_ats      127/127 company boards succeeded
  ingest_jsearch  21/21 queries succeeded
  ingest_adzuna   67/70 queries succeeded; the rest fail on Adzuna connection resets

Neon after the first collection:
  4,996 postings stored, 3,929 canonical, 1,067 linked as duplicates, 1,586 companies
  canonical by region:  us 1,628 (1,178 full text)   eu 1,500 (293)
                        uk 637 (213)                 gulf 164 (75)
  827 canonical postings state a salary

Idempotency: re-running all 127 boards inserted 1 row — a genuinely new posting —
instead of duplicating the 1,693 already stored.
```

### Notes

- **Adzuna's API resets about half of new connections.** Measured on 2026-09-17: 6/10 TLS
  handshakes to `api.adzuna.com` succeeded, while `s3.us-west-2.amazonaws.com`,
  `dynamodb.us-west-2.amazonaws.com`, `boards-api.greenhouse.io` and `www.adzuna.co.uk`
  managed 10/10 from the same machine. A connection that never opens costs no quota, so
  `get_json` now retries five times with growing waits, which recovered most failures.
  A few queries still fail per run; the next weekly run collects them.
- **A DAG whose last task always runs can hide failures.** `link_duplicates` uses
  `all_done`, so the first Adzuna run was marked successful while 10 queries had failed.
  Each ingest DAG now ends with a task that fires only on failure and fails the run.
- **Your JSearch key is an OpenWeb Ninja key, not RapidAPI** (RapidAPI returned 403, not
  subscribed). The variable is now `JSEARCH_API_KEY` and the client calls
  `api.openwebninja.com/jsearch/search-v2`.
- **Cloudflare-style boards put the work arrangement in the location** ("Hybrid",
  "In-Office"). Office names are now used when a location names no place at all, which
  recovered 24 in-scope Cloudflare postings.
- Some board postings are years old (earliest 2019-11-14): openings left listed. Phase 4
  should restrict counts to a recent window.
- Aggregators repost heavily: 611 Adzuna and 211 JSearch rows were reposts of a job
  already stored from the same source, versus only 29 that matched a company board.

### Deferred (deliberately)

- `raw.postings.description_text` is still full text; trimming to 1,000 characters
  happens in phase 3, after extraction succeeds.
- Re-extraction staleness: when a posting's text changes, its stored extraction is stale.
  Phase 3 should key extractions on `content_hash` as well as model and prompt version.
- Gulf coverage rests on JSearch plus four company boards; more Gulf employers on public
  boards would help.

### Next

Phase 3 — extraction. First task is the schema spike: whether `responseJsonSchema` works
for `gemma-4-*` on the Gemini API. Then the LLM interface with Gemini and Ollama backends,
the quota governor (25 RPM / 13,000 per day), a 50-posting golden set and `run_eval`.

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

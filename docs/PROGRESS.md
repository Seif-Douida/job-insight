# Progress log

Running record of what exists, what was verified, and what comes next.
Newest entry first. Update before every phase-closing commit.
Mistakes and what they taught live in [lessons.md](lessons.md).

## Phases

| # | Phase | Status |
| --- | ----- | ------ |
| 1 | Foundation — repo, config, schema, Airflow up | done 2026-09-17 |
| 2 | Ingestion — ATS boards, Adzuna, JSearch, dedupe | done 2026-09-17 |
| 3 | Extraction — LLM backends, quota governor, eval | done 2026-09-18 |
| 4 | Modeling — dbt staging → marts, taxonomy | done 2026-09-18 |
| 5 | Dashboard — Next.js pages and API routes | in progress |
| 6 | Ops — Oracle VM deploy, schedules, Vercel | not started |

---

## 2026-09-18 — Phase 5: Dashboard (in progress)

The pages that answer the question the project set out to answer are live locally. The
comparison and per-skill views are not built yet, so the phase stays open.

### Built

- `web/` — Next.js 16.3 (App Router, React 19, TypeScript), no CSS framework and no chart
  library. The bars are `div`s; a dependency to draw a rectangle is not worth its build.
- Pages: the front page, one page per role and region, `/methodology`, and a 404 that
  sends people back to the matrix.
- **The front page is the coverage matrix.** Seven roles by four regions, each cell the
  number of postings behind that cohort, greyed and dotted when under 25. Choosing a
  cohort and seeing how much evidence backs it are the same action, which is the honest
  way to open a site whose subject is how much you can trust a percentage.
- **The measure column carries two facts in one colour.** Bar length is the share of
  postings naming a skill; the solid part of the bar is the share of those mentions
  written as a requirement, the hatched remainder the share written as a preference. So
  "Machine learning, required in 17% of mentions" draws as a nearly all-hatched bar and
  reads instantly as *often named, rarely insisted on*.
- `lib/queries.ts` — every read the site makes, each wrapped in `use cache` with an hourly
  lifetime. Counts and shares are cast in SQL, because node-postgres returns `numeric` and
  `bigint` as strings and a percentage arriving as `"0.703"` formats as `NaN` three files
  later.
- `lib/db.ts` — takes `sslmode` out of the shared connection string and states the TLS
  policy in code. node-postgres reads `sslmode=require` as full verification today but has
  announced it will weaken to libpq semantics in a future major, which would change what
  the code does without changing the code.
- `/methodology` renders `docs/methodology.md` rather than restating it. One copy: a
  methodology page that has drifted from the method is worse than none.
- `pipeline/tests/test_taxonomy_labels.py` — the dashboard keeps its own display labels so
  it needs no YAML parser for eleven strings; these four tests fail if they ever drift
  from `roles.yaml` and `regions.yaml` in either direction.
- `/role/[role]` — the role across all four regions, ranked by how far apart they are, and
  what changes with experience. Only cohorts large enough to rank on decide the order; thin
  ones are still shown but do not get a vote, or the top of the table fills with noise from
  a sixteen-posting sample.
- `/skill/[skill]` — which roles and regions ask for one skill. Thinness is marked per cell
  here rather than per column, because the columns pool regions while each cell is a single
  cohort: without it, "MLOps Engineer, Gulf, 100%" reads as solid when it rests on six
  postings.
- `/compare/[region]/[a]/[b]` — two roles side by side, as a bar running left and right
  from the skill name. Answers the question the titles do not: a US Analytics Engineer
  posting names SQL in 100% of cases against a Data Engineer's 48%, and Spark in 4%
  against 44%. The second series is plain ink rather than a second accent colour, so the
  page still spends colour in one place.
- `pipeline/tests/test_skill_slugs.py` — no two skills may share a URL, and no two
  canonical names may differ only by case or punctuation.

### Fixed along the way

Building the skill pages surfaced two skills stored under two canonical names each —
`Hugging Face`/`HuggingFace` and `Infrastructure as code`/`infrastructure-as-code`. Each
had its demand split across both spellings and was showing about half its real figure. The
seed is corrected and a test now fails on any repeat; see [lessons.md](lessons.md).

### Decided

- **Server components, not route handlers.** Nothing outside these pages consumes the
  data, so an API layer would exist only to be called by our own pages. It can be added
  the day something external needs it.
- **Cached, not live.** The marts are rebuilt once a day, so every page is a cached shell.
  A live query per request would add latency and keep a free-tier Neon compute awake for
  no benefit.

### Verified

```text
$ npm run build
✓ Generating static pages (169/169)
  28 cohorts, 7 roles, 60 skills and 59 role comparisons prerendered, revalidate 1h

$ npm run lint          # eslint, 0 problems
$ pytest -q             # 202 passed
$ ruff check pipeline && black --check pipeline     # clean, 59 files
$ dbt build             # PASS=25 after the alias fix

Page against SQL — Data Engineer / US:
  page  101 openings, 45 companies, 26 March–17 September 2026, 6 yrs, 31% remote, 12% visa
  SQL   101, 45, 2026-03-26, 2026-09-17, 6.0, 0.31, 0.12          match
  page  Python 70% (71 of 101), Spark 44%, USD median $233,500 (n=11)
  SQL   0.703, 0.436, 233500.0, 11                                match

No horizontal page scroll at 360px on any of the six routes; checked light and dark.
```

### Next

Every page in the design is built. One acceptance item is outstanding before the phase
closes: Playwright smoke tests per route, so a mart changing shape fails a test rather than
a page. Top hiring companies per cohort is not built — it would need a new mart. Trend and
co-occurrence stay deferred: there is no history to plot yet.

Deployment is phase 6, with one constraint discovered here: `/methodology` reads a file
from the repository root, so Vercel's root directory stays at the repository root with the
build command `cd web && npm run build`.

---

## 2026-09-18 — Phase 4: Modeling (done)

### Built

- `pipeline/dbt/` — dbt project against Neon, everything landing in one `analytics`
  schema. Layers are told apart by name (`stg_`, `int_`, `mart_`), which at this size is
  clearer than a schema each.
- Staging: `stg_postings` (canonical only), `stg_extractions` (newest successful
  extraction per posting), `stg_skill_mentions` (the skills array flattened).
- `seeds/skill_aliases.csv` — 449 aliases onto 414 canonical skills, generated by
  `pipeline/taxonomy/build_skill_aliases.py` and then maintained by hand. The join is
  case-insensitive, so only genuine differences of wording need an entry.
- Intermediate: `int_skill_mentions` (canonical name attached), `int_postings_enriched`
  (everything a mart groups by), `unmapped_skills` (the review queue).
- Marts: `mart_role_region_summary`, `mart_skill_demand`, `mart_skill_by_seniority`,
  `mart_salary`. Every row carries its sample size and a `low_confidence` flag.
- Five singular data tests: percentages inside 0..1, `n_with_skill <= n_total`, every
  cohort states its size, one row per cohort, salary percentiles ordered and annual.
- `pipeline/dags/transform.py` — `dbt build` daily at 08:00, two hours after extraction.
  It passes `--no-partial-parse`: the repo is mounted, so dbt's parse cache in
  `target/` may have been written by the host's dbt under a different Python.
- `pipeline/db/dbt_profile.py` — derives `profiles.yml` from `DATABASE_URL`, so the
  credentials are still written down exactly once.

### Verified

```text
$ dbt build
Done. PASS=25 WARN=0 ERROR=0 SKIP=0 TOTAL=25

$ pytest -q
187 passed

Airflow transform run (manual__2026-09-18T21:10): both tasks success
  mart_role_region_summary      28 rows      mart_skill_demand        3,457 rows
  mart_skill_by_seniority    3,939 rows      mart_salary                 21 rows

What do companies in the USA want from a Data Engineer? (90 postings, last 180 days)
  Python 71.1% (64, 92% required)   SQL 50.0% (45, 98%)   Spark 46.7% (42, 88%)
  Airflow 45.6% (41, 74%)           Snowflake 42.2% (38)  dbt 38.9% (35)

Publishable cohorts (n >= 25): 18 of 28
                       us      eu      uk    gulf
  ai-engineer         239     108      44      27
  ml-engineer         247      42      78     18*
  data-scientist      163      68      55     22*
  data-engineer       101      54      30     16*
  data-analyst         70      66      57     19*
  mlops-engineer       68     16*     22*      6*
  analytics-engineer   26     17*     17*      5*
```

### Notes

- **Skill names fragment by casing and by wording, and only the second is worth a file.**
  Matching case-insensitively means "Python"/"python" collapse for free. 449 aliases cover
  65.8% of mentions; 60% of distinct names appear exactly once and are only 12% of
  mentions, so the long tail is left unmapped and counted in `unmapped_skills` instead.
- **A 180-day window.** 65% of the corpus is under 90 days old and only 126 postings are
  over a year, so this drops almost nothing while keeping 2019 openings out of a 2026
  percentage.
- **The first salary mart published nonsense** — a 25th percentile of 55 EUR. About one in
  nine "stated" salaries is not annual: hourly rates stored as `10-10` EUR, `18-25` GBP,
  and rows whose minimum is 0 meaning "not stated". No source gives a pay period, so the
  mart now keeps only figures that read as annual pay in USD, EUR or GBP, and a data test
  fails the build if a median falls outside that band. It cost about a quarter of the
  salary rows and was still right: a median over mixed hourly and annual figures is not a
  weaker number, it is a false one.
- **Salary roles come from the title matcher, not the model.** Most postings that state pay
  are excerpts, which are never extracted. That is a weaker signal than the 84%-accurate
  classifier and has to be said wherever the figures appear.
- Seniority is the axis where the corpus is richest after role: 19 role-and-level cohorts
  clear 25. For ML engineers, LLM rises 0 -> 37% -> 46% from mid to principal while
  TensorFlow leaves the top six entirely.

### Deferred (deliberately)

- `mart_skill_trend` needs weeks of collection before it shows anything; there is no
  historical backfill to fake it with.
- `mart_skill_cooccurrence` is worth having for the skill detail page, and is not needed
  before the dashboard exists.
- The Gulf publishes exactly one cohort (`ai-engineer`, n=27). More Gulf employers on
  public boards is the only real fix.

### Next

Phase 5 — the dashboard. Next.js on Vercel reading these marts, with the role-and-region
page first, since it is the one that answers the question the project set out to answer.

---

## 2026-09-18 — Coverage: SmartRecruiters and a bigger company list

Between phases 3 and 4, because building marts on a knowingly biased sample would mean
re-cutting them later.

### Built

- `pipeline/ingest/smartrecruiters.py` — a fourth ATS source. Its list endpoint carries no
  description, so `fetch_postings` filters on the title and ISO country the list *does*
  carry, and spends a second request only on survivors: about 100 detail calls on a
  4,800-posting board instead of 4,800. `companyDescription` is excluded from the stored
  text, since that is the "About us" blurb that produced empty extractions in phase 3.
- `survey()` on the same module, used by `probe_boards`: counting a board's in-scope
  postings needs no descriptions, so probing costs a few requests instead of one per job.
- `companies.yaml` grown from 127 to 158 boards after probing 172 candidates.
- US state names completed in `regions.yaml` ("Bellevue, Washington" resolved to nothing
  while "Seattle, Washington" resolved, because only some states were listed).

### Verified

```text
$ pytest -q
174 passed

Airflow ingest_ats (manual__2026-09-18T15:49): 161 task instances, 160 success, 1 skipped
  (the failure watcher, correctly skipped because nothing failed)

Neon after the run:
  source            canonical   full text
  adzuna              2,041           0
  greenhouse          1,150       1,150
  ashby                 664         664
  smartrecruiters       173         170
  jsearch               154          65
  lever                  50          50

  5,339 postings stored, 2,188 with full text (was 1,778)
```

### Notes

- **The new source found companies the others could not.** Wise (43 in-scope postings) and
  Delivery Hero (18) publish on SmartRecruiters and were invisible to us before. Adding the
  source to `BOARD_SOURCES` put it into `probe_boards` automatically.
- Bosch alone yields 101 postings, 99 of them full text averaging 3,341 characters, spread
  across PT, DE, US and RO — the EU coverage the ATS list was thinnest on.
- **Probe hit rate is ~40%** (69 boards from 172 candidates), and a board averages ~13.7
  in-scope postings. Growing the corpus further is mechanical: more candidate names.
- Postings are not all in English now. Skill names largely survive
  ("Python", "Kubernetes"); descriptive skills may not. Recorded in methodology.md as a
  limit rather than assumed away.

### Next

Phase 4 — modelling, on a corpus of 2,188 full-text postings rather than 1,778.

---

## 2026-09-18 — Phase 3: Extraction (done)

### Built

- `pipeline/extract/schema.py` — `Extraction` and `ExtractedSkill`, the contract every
  answer is validated against; an unknown role degrades to `other` instead of failing
- `pipeline/extract/prompt.py` — prompt `v2`, with the role guide, skill-naming rules and
  the JSON schema sent as `responseJsonSchema`
- `pipeline/extract/llm/` — the `LlmBackend` protocol and `GeminiBackend`; swapping models
  is a config change
- `pipeline/extract/quota.py` — `DailyQuota` (counted in Postgres, so a restart cannot
  double-spend) and `Pacer`, which holds a rolling minute of **input tokens** as well as
  requests
- `pipeline/extract/run.py` — `extract_pending`: threaded, commits every 20, records every
  outcome, and leaves rate-limited postings untouched
- `pipeline/extract/archive.py` — writes full text to gzipped JSONL, then trims the column
- `pipeline/eval/` — 19 hand-written label sets, `build_golden_set`, `score.py`, `run_eval`
- `pipeline/dags/extract.py` — daily 06:00, extraction then archive
- `infra/sql/002_extraction_content_hash.sql`, `003_posting_role_hint.sql`
- [lessons.md](lessons.md) — the mistakes made so far and the rule each produced

### Verified

```text
$ pytest -q
166 passed in 6.57s

$ ruff check pipeline && black --check pipeline
All checks passed!
52 files would be left unchanged.

Airflow: both extract runs finished green (scheduled__2026-09-17T06, manual__20:52)

Neon after the backlog run (prompt v2, gemma-4-26b-a4b-it):
  1,736 ok   21 error   2 invalid_json   35 still pending
  13.88 skills per posting on average (1.8 before excerpts were excluded)

Archive and trim:
  data/archive/postings-2026-09.jsonl.gz   1,736 rows, one per successful extraction
  1,712 postings trimmed to exactly 1,000 characters
  database size 27 MB of the 0.5 GB free tier
```

### Notes

- **The free tier limits input tokens per minute, not requests.** Pacing at 25 RPM under a
  documented 30 RPM limit still drew 429s on 18% of calls. The API's own error names the
  quota: `GenerateContentInputTokensPerModelPerMinute-FreeTier`, limit 16,000. A posting
  costs about 2,000 input tokens, so the budget runs out near 8 requests a minute.
- **The retries made it worse.** A 429 was retried five times inside the request, and those
  retries never passed through the pacer, so each incident fired six unpaced calls and the
  error rate climbed from 11% to 18% as the run went on.
- **Measured after the fix**, same model, on a fresh 370-posting run:

  | | before | after |
  | --- | ------ | ----- |
  | Successful extractions | ~7.0/min | **8.7/min** |
  | Requests refused (429) | ~14% | 5.4% |
  | Postings charged an attempt for a rate limit | 259 | 0 |

  Faster *and* cleaner, once the budget was tuned to 15,000 estimated tokens per minute.
  Rate limits did not disappear — the budget deliberately sits close enough to the 16,000
  ceiling that a dense minute still overshoots — but they are now harmless: the run waits
  exactly as long as the server asks and the posting stays pending, unpenalised.
  Those 20 postings were collected by the next run.
- **Excerpts are not sent to the model.** The first live run averaged 1.8 skills per
  posting; the inputs turned out to be 500-character "About us" blurbs. Extraction now
  requires `text_quality = 'full'`, and excerpts take their role from `role_hint`
  (backfilled for 3,728 rows).
- Trimming updates `description_text` only, so `content_hash` still matches what the
  source serves and a re-ingest will not undo the trim.
- Of the 23 non-ok extractions, 20 are rate limits from the old pacer (attempts 1 of 3,
  so the next daily run retries them), 1 is an answer cut off at the token limit, and
  2 returned an empty skill name that validation rejected.

### Deferred (deliberately)

- 35 postings remain pending; the daily run collects them rather than a special pass.
- `gemma-4-31b-it` still answers 500/503, so the smaller `26b-a4b` does the work. Worth
  re-testing before phase 4 concludes.
- The golden set is 19 postings labelled by a language model. Growing it, and having a
  second reader disagree with it, would do more for confidence than any prompt change.
- Ollama backend: the local GPU is too small for a model worth comparing.

### Next

Phase 4 — modelling. dbt staging → marts, the `skill_aliases.csv` taxonomy and its
unmapped-skill review loop, the `n >= 25` guardrail, and restricting counts to a recent
window (postings date back to 2019).

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

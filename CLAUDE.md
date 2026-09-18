# Job Insight — working notes

Read [docs/design.md](docs/design.md) for the design and [docs/PROGRESS.md](docs/PROGRESS.md)
for what is built, verified and next. Update PROGRESS.md at the end of every phase.
[docs/lessons.md](docs/lessons.md) records the mistakes made so far and the rule each one
produced — worth reading before repeating one, and worth adding to when a new one costs
real time.

## Layout

```text
pipeline/      Python: ingestion, extraction, dbt models, Airflow DAGs
  dags/        Airflow DAG definitions (mounted into the container)
  ingest/      one client per source + shared normalization/dedupe
  extract/     LLM backends, extraction schema, quota governor
  taxonomy/    roles.yaml, regions.yaml, companies.yaml, skill aliases
  eval/        golden set + evaluation harness
  dbt/         staging → intermediate → marts
  tests/       pytest suite
web/           Next.js dashboard (Vercel)
infra/         docker-compose, SQL schema, .env.example
docs/          design, methodology, PROGRESS log
```

## Setup

```bash
cp infra/.env.example .env          # then fill in the credentials
python -m pip install -e ".[dev]"
python -m pipeline.db.migrate       # applies infra/sql/*.sql to $DATABASE_URL (idempotent)
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml exec postgres createdb -U airflow jobinsight_test  # once
```

Storage tests run against `TEST_DATABASE_URL` (the compose Postgres on port 5433) and
are skipped when it is unset. They truncate tables, so it must never point at Neon.
After editing `.env`, recreate Airflow so it sees the change:
`docker compose -f infra/docker-compose.yml up -d --force-recreate airflow`.

Airflow UI: <http://localhost:8080>. The admin password is printed in the container logs
(`docker compose -f infra/docker-compose.yml logs airflow | grep -i password`).

## Commands

```bash
pytest pipeline/tests                # unit tests
ruff check pipeline && black --check pipeline
python -m pipeline.ingest.probe_boards <slug>...   # find a company's job board for companies.yaml
python -m pipeline.eval.run_eval [model] [--verbose]  # extraction accuracy on the golden set
python -m pipeline.eval.build_golden_set           # after adding labels to eval/labels.json
cd pipeline/dbt && dbt build         # models + data tests
cd web && npm run dev                # dashboard
```

## Conventions

- **Small modules, one job each.** One file per source client, one per LLM backend.
- **Type hints on anything public**; Pydantic models for external data at the boundary.
- **No new infrastructure without a phase that needs it.** Explicitly out of scope unless a
  real need shows up: queues, caches, auth, a separate API service, request batching.
- **Idempotent by default.** Re-running any ingest or transform must not duplicate rows.
- **Secrets only in `.env`.** Every new variable gets an entry in `infra/.env.example`.
- **Never mix `text_quality` values inside one percentage.** Context-dependent fields
  (required vs. nice-to-have, seniority, sponsorship) come only from `full` postings.
- **Every published aggregate carries its sample size `n`.**
- A phase is done when its tests pass, its verification command has been run, PROGRESS.md
  records the real output, and the work is committed and pushed.

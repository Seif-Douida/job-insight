# Deploying

Three pieces, in three places, none of which cost anything:

| Piece | Where | What it does |
| ----- | ----- | ------------ |
| Airflow and the pipeline | Oracle Cloud Always Free VM | Collects, extracts, rebuilds the marts |
| Postgres | Neon free tier | Holds everything, raw through marts |
| Dashboard | Vercel Hobby | Reads the marts |

The server writes, the dashboard reads, and they never talk to each other. That is what
lets each be deployed, broken and fixed on its own.

---

## Part 1 — the server

### Create the machine

In the Oracle Cloud console: **Compute → Instances → Create instance**.

- **Shape:** Ampere A1 (ARM), 2 OCPU and 12 GB is plenty. The Always Free allowance is 4
  OCPU and 24 GB across all your ARM instances.
- **Image:** Ubuntu 24.04.
- **SSH key:** upload your public key. There is no password login.
- **Networking:** leave the default security list alone. **Do not open port 8080.** The
  Airflow UI can trigger every DAG and read every credential the stack holds; it is bound
  to the server's loopback interface and reached through an SSH tunnel instead.

> ARM capacity is genuinely scarce in some regions and "Out of host capacity" is common.
> Retry over a few days, or fall back to a small paid VPS — nothing here is Oracle-specific.

### Install and start

```bash
ssh ubuntu@<server-ip>
curl -fsSL https://raw.githubusercontent.com/Seif-Douida/job-insight/main/infra/deploy/bootstrap.sh | bash
```

It installs Docker, clones the repository to `~/job-insight`, and stops after creating
`.env` from the example. Fill that in:

```bash
nano ~/job-insight/.env
```

| Variable | Notes |
| -------- | ----- |
| `DATABASE_URL` | The Neon connection string, same one used locally |
| `GEMINI_API_KEY` | Google AI Studio |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | |
| `JSEARCH_API_KEY` | OpenWeb Ninja |
| `AIRFLOW_DB_PASSWORD` | `openssl rand -hex 24`. Only used between the two containers |
| `ALERT_WEBHOOK_URL` | Optional, see Part 3. Worth setting |

Then run it again. It refuses to start if a required value is missing, which is better than
starting and failing in a task log at three in the morning.

```bash
bash ~/job-insight/infra/deploy/bootstrap.sh
```

### Reach the UI

From your own machine, not the server:

```bash
ssh -N -L 8080:localhost:8080 ubuntu@<server-ip>
```

Leave that running and open <http://localhost:8080>. The admin password is in the logs:

```bash
docker compose -f infra/docker-compose.prod.yml logs airflow | grep -i password
```

It is regenerated whenever the container is recreated, so read it again after an update
rather than saving it.

### Turn the DAGs on, in order

**Airflow pauses every new DAG by default.** A paused DAG accepts a trigger and queues
forever, which looks identical to working — this cost an afternoon in phase 4 and is
written up in [lessons.md](lessons.md).

Unpause and verify one at a time, checking each before moving on:

1. `db_healthcheck` — trigger it manually. It proves the container can read the taxonomy
   and reach Neon. If this fails, nothing else is worth trying.
2. `ingest_ats` — the daily 03:00 collection. Watch one run finish green.
3. `extract` — 06:00. Check `raw.extractions` grows and no task is stuck retrying.
4. `transform` — 08:00. It ends with the dbt data tests, so green here means the marts are
   publishable.
5. `ingest_adzuna` (Mondays) and `ingest_jsearch` (1st and 15th) — these spend a metered
   monthly quota, so turn them on last and deliberately.

A run's state answers "is anything still pending", not "is anything going well". Read the
task-level states.

---

## Part 2 — the dashboard

### Import the project

In Vercel: **Add New → Project**, import the GitHub repository.

- **Root Directory:** leave it at the repository root. Do **not** set it to `web/`.
  `vercel.json` already points the build at `web`, and the methodology page is generated
  from `docs/methodology.md` — with the root set to `web/` that file is not in the upload
  and the build fails.
- **Framework:** Next.js, detected automatically.

### Environment variable

Add one, for all environments:

| Name | Value |
| ---- | ----- |
| `DATABASE_URL` | The Neon **pooled** connection string — the host containing `-pooler` |

Use the pooled endpoint rather than the direct one. Each serverless instance opens its own
connections, and the pooler is what keeps a burst of them from exhausting the free tier's
limit.

### Deploy and check

Push, or press Deploy. Then confirm the three things worth confirming:

- The front page shows a matrix of numbers, not zeroes.
- `/methodology` renders — this is the page that fails if the root directory is wrong.
- A cohort page's figures match the database:

  ```sql
  select n_postings, n_companies from analytics.mart_role_region_summary
  where role = 'data-engineer' and region = 'us';
  ```

---

## Part 3 — alerts

Without this, an overnight failure is recorded and nobody is told.

Create an incoming webhook — Discord (**Server Settings → Integrations → Webhooks**), Slack
(**Incoming Webhooks**) or ntfy. Any of them works; the alert sends its text under both the
keys those services read, so there is nothing to configure beyond the URL.

```bash
nano ~/job-insight/.env          # ALERT_WEBHOOK_URL=https://...
docker compose -f infra/docker-compose.prod.yml up -d --force-recreate airflow
```

Test it without waiting for something to break:

```bash
docker compose -f infra/docker-compose.prod.yml exec airflow \
  python -c "from pipeline.alerts import send_alert; print(send_alert('job-insight: alerts are working'))"
```

The URL is a credential — anyone holding it can post as you. It is never logged, never put
in a message, and httpx's own request logging is suppressed for that one call so it cannot
reach a task log either.

One alert is sent per failed **run**, not per failed task, because the ingest DAGs map a
task across 185 company boards.

---

## Keeping it up to date

**Dashboard code.** Push to `main`. Vercel builds and deploys automatically; pull requests
get their own preview URL. GitHub Actions runs lint, typecheck and the smoke tests on the
way, so a broken build is caught before it is live. Add `DATABASE_URL` as a repository
secret to enable the build-and-smoke-test half of that job.

**Pipeline code.** On the server:

```bash
bash ~/job-insight/infra/deploy/update.sh
```

It pulls, and restarts. It rebuilds the image only when `pyproject.toml` or the Dockerfile
changed — the repository is mounted, so a DAG edit is a restart rather than a five-minute
rebuild on a small ARM box.

**Data.** Nothing. This is the part worth understanding: the dashboard pages are
prerendered but revalidate hourly, so the marts `transform` writes each morning reach the
site within the hour with no build and no deploy. That is why the pages are cached server
components rather than a static export — a static site would need a rebuild every time a
posting was collected.

---

## When something breaks

```bash
cd ~/job-insight
docker compose -f infra/docker-compose.prod.yml ps          # is it running
docker compose -f infra/docker-compose.prod.yml logs --tail 100 airflow
df -h                                                        # disk: the usual culprit
```

- **A DAG is "queued" and never starts.** It is paused, or a previous run of the same DAG
  is still active (`max_active_runs=1`).
- **A run says "running" for a long time.** A failed task waiting out its retry delay looks
  exactly like a working one at run level. Open the task and read its state.
- **Disk filling.** Container logs are capped at 10 MB each. Airflow's task logs are not;
  clear old ones and trim the metadata database:

  ```bash
  docker compose -f infra/docker-compose.prod.yml exec airflow \
    find /opt/airflow/logs -type f -mtime +30 -delete
  docker compose -f infra/docker-compose.prod.yml exec airflow \
    airflow db clean --clean-before-timestamp "$(date -d '90 days ago' +%Y-%m-%d)" --yes
  ```

- **`dbt_build` fails with a `KeyError` inside dbt's parser.** A stale parse cache in the
  mounted `pipeline/dbt/target/`. `update.sh` clears it; the DAG also passes
  `--no-partial-parse`.
- **The dashboard shows stale numbers.** Expected for up to an hour after `transform`
  runs. If it lasts longer, check the `transform` DAG actually went green.

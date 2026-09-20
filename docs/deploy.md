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

### First, make an SSH key

Do this before opening the wizard, because the wizard asks for it and will not let you
past without one.

Oracle turns off password login entirely. Instead you generate a **key pair**: two matching
files. The *private* key stays on your laptop and is never sent anywhere. The *public* key
is copied onto the server. When you connect, the two are checked against each other without
the private key ever crossing the network — which is why this is safer than a password, and
why a stolen server tells an attacker nothing about how to get back in.

In PowerShell on your own machine:

```powershell
ssh-keygen -t ed25519 -C "job-insight"
```

It asks three things:

1. **Where to save it.** Press Enter for the default, `C:\Users\<you>\.ssh\id_ed25519`.
2. **A passphrase.** Setting one means the key is useless to anyone who copies the file.
   You will type it when connecting, unless you start Windows' `ssh-agent` service to
   remember it. Pressing Enter twice leaves it unprotected, which is common for a personal
   cloud VM but means the file alone is enough to log in as you.
3. **The same passphrase again.**

You now have two files in `C:\Users\<you>\.ssh\`:

| File | What it is |
| ---- | ---------- |
| `id_ed25519` | **Private.** Never upload it, never paste it, never commit it. Nothing legitimate ever asks for this file |
| `id_ed25519.pub` | Public. This is the one Oracle wants. It is safe to share |

The `.pub` is the short one — a single line starting `ssh-ed25519`.

### Create the machine

In the Oracle Cloud console: **Compute → Instances → Create instance**.

**Shape and image.** Click **Edit** beside "Image and shape".

- **Image:** Ubuntu 24.04 (Canonical Ubuntu).
- **Shape:** the **Ampere** tab, `VM.Standard.A1.Flex`. Set 2 OCPU and 12 GB. Check the
  line says **Always Free eligible** before continuing — the default shape often is not,
  and this is the step where an unwanted bill starts.

**Networking.** A brand-new Oracle account has no network yet, so the "Virtual cloud
network" and "Subnet" dropdowns are empty and cannot be picked from. Create both here:

- **Primary network:** choose **Create new virtual cloud network**, not "Select existing".
- **Subnet:** choose **Create new public subnet**, not "Select existing".
- Leave the generated names as they are.
- Scroll to **Public IPv4 address assignment** and turn **Automatically assign public IPv4
  address** *on*. It may be off, and the warning "You must select a public subnet to assign
  a public IPv4 address" clears once the public subnet above is chosen. **Without a public
  IP the machine has no internet-facing address and you cannot SSH to it at all.**
- **IPv6:** leave off. Nothing here needs it.

**SSH keys.** Choose **Upload public key file (.pub)** and select
`C:\Users\<you>\.ssh\id_ed25519.pub`. The `.ssh` folder is hidden, so if the file picker
does not show it, paste the full path into the filename box.

> Do not pick "Generate a key pair for me" unless you are ready to download the private key
> immediately — Oracle shows it once and never again.

**Boot volume.** The defaults are fine.

Create the instance, then copy its **Public IP address** from the instance page. That is the
`<server-ip>` used everywhere below.

**What is open to the internet.** Creating the VCN this way gives it a default security list
that allows inbound SSH on port 22 and nothing else. That is exactly what we want — leave it
alone. In particular **do not open port 8080**: the Airflow UI can trigger every DAG and
read every credential the stack holds, so it stays bound to the server's loopback interface
and is reached through an SSH tunnel instead.

> ARM capacity is genuinely scarce in some regions and "Out of host capacity" is common.
> Retry over a few days, try a different availability domain, or fall back to a small paid
> VPS — nothing here is Oracle-specific.

### If the instance has no public IP

The instance page shows `Public IPv4 address: -` and only a private `10.0.0.x`. The
**Automatically assign public IPv4 address** toggle was left off. This is recoverable
without rebuilding, provided the subnet is a public one — a subnet is public or private at
creation and cannot be changed afterwards.

**Check the subnet first.** Instance → **Networking** → click the **Subnet** link. Its
detail page has an **Access type**: either "Public Subnet" or "Private Subnet".

**If it says Public Subnet**, add the address to the existing instance:

1. Instance → **Networking** → under **Attached VNICs**, click the primary VNIC.
2. Find the **IPv4 Addresses** list.
3. On the row holding the private address, open the **⋮** menu → **Edit**.
4. Set **Public IP type** to **Ephemeral public IP**, leave the name blank, **Update**.

The address appears on the instance page within a few seconds. Ephemeral is fine here: it
is kept for the life of the instance and only changes if the instance is terminated. A
reserved IP survives termination, which matters only once something points a domain at it.

**If it says Private Subnet**, the instance cannot reach the internet and cannot be given a
public address. An instance's primary VNIC cannot move between subnets, so terminate it and
create a new one, this time choosing **Create new public subnet**. Nothing is lost —
nothing has been installed yet.

**While you are there**, confirm two things the VCN needs for SSH to work at all. Both are
set up automatically when the wizard creates the network, so this is a check rather than a
task:

- **VCN → Route Tables → the default table** has a rule `0.0.0.0/0` → target **Internet
  Gateway**. Without it, traffic has a public address but no way out.
- **VCN → Security Lists → the default list** has an ingress rule allowing TCP port **22**
  from `0.0.0.0/0`. That is the only port that should be open.

### First connection

```powershell
ssh ubuntu@<server-ip>
```

The username is `ubuntu` because the image is Ubuntu. The first connection asks you to
confirm the server's fingerprint; type `yes`.

If it refuses with `Permission denied (publickey)`, the usual causes are that the instance
got no public IP, or that a different key was uploaded than the one `ssh` is offering. Point
at the key explicitly to check: `ssh -i C:\Users\<you>\.ssh\id_ed25519 ubuntu@<server-ip>`.

### Install and start

```bash
ssh ubuntu@<server-ip>
curl -fsSL https://raw.githubusercontent.com/Seif-Douida/job-insight/main/infra/deploy/bootstrap.sh | bash
```

**Expect to run this more than once.** It is written to be repeated, and it stops on purpose
at two points:

1. **After creating `.env`**, so you can fill in the credentials.
2. **After installing Docker**, if this is the first time. Linux decides what groups a
   session belongs to when the session starts, so the shell that installed Docker is not yet
   allowed to use it. Disconnect, reconnect, and run the script again — everything already
   done is skipped.

On a machine booted minutes ago, Ubuntu is still running its own automatic updates and holds
the package lock. The script waits for that rather than failing on it; if you see "Waiting
for Ubuntu's automatic updates to finish", nothing is wrong.

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
| `AIRFLOW_DB_PASSWORD` | A long random string — see below. No human ever types it |
| `ALERT_WEBHOOK_URL` | Optional, see Part 3. Worth setting |

Most of those you already have in the `.env` on your own machine. Rather than retyping
them, copy the file across and then fill in the two the server needs:

```powershell
scp C:\Users\<you>\...\market_insights\.env ubuntu@<server-ip>:~/job-insight/.env
```

#### About AIRFLOW_DB_PASSWORD

There are **two** databases in play, and they do different jobs:

- **Neon** holds the project's data — postings, extractions, marts. That is `DATABASE_URL`.
- **A second Postgres**, running in a container next to Airflow, holds Airflow's own
  bookkeeping: which DAG ran when, what state each task reached, where its log is. Airflow
  cannot run without somewhere to keep that, and it is deliberately kept off Neon so a
  scheduler writing thousands of rows a day never touches the free tier holding the data.

`AIRFLOW_DB_PASSWORD` is the password those two containers use with each other. You will
never type it, and nothing outside the machine can reach that database — the server stack
gives it no port at all. It exists so that a mistake elsewhere, someone exposing a port or
another container on the same network, does not find `postgres/postgres` waiting.

Which is why it should be long and random rather than memorable. On the server:

```bash
openssl rand -hex 24
```

`openssl` is the standard cryptography toolkit and is already installed; `rand -hex 24`
asks it for 24 random bytes printed as hexadecimal, which is 48 characters like
`9f3c1a...`. It is just a random-string generator — there is nothing to remember and
nothing to look up later.

Copy the output into `.env`, or set it in one step without copying anything:

```bash
cd ~/job-insight
sed -i "s|^AIRFLOW_DB_PASSWORD=.*|AIRFLOW_DB_PASSWORD=$(openssl rand -hex 24)|" .env
grep -c '^AIRFLOW_DB_PASSWORD=.\{48\}$' .env     # prints 1 when it worked
```

> **Set this before the first start.** Postgres reads the password only when it first
> creates its data directory. Changing it afterwards has no effect, because the database
> already exists with the old one — and the symptom is Airflow failing to authenticate
> against its own metadata store. If that happens: `docker compose -f
> infra/docker-compose.prod.yml down -v` wipes the Airflow database and lets it initialise
> again. That deletes run history only; nothing in Neon is touched.

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

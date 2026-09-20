#!/usr/bin/env bash
#
# Prepare a fresh Ubuntu server to run the pipeline, then start it.
#
#   curl -fsSL https://raw.githubusercontent.com/Seif-Douida/job-insight/main/infra/deploy/bootstrap.sh | bash
#
# or, once the repository is cloned:  bash infra/deploy/bootstrap.sh
#
# Safe to run twice. It installs Docker if missing, clones the repository if missing, and
# stops before starting anything if the credentials are not filled in — a stack that boots
# without them fails later, in a task log, instead of here where someone is watching.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Seif-Douida/job-insight.git}"
REPO_DIR="${REPO_DIR:-$HOME/job-insight}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# --- Docker ------------------------------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "Added $USER to the docker group. Log out and back in for it to take effect."
fi

if ! docker compose version >/dev/null 2>&1; then
  say "Installing the Docker Compose plugin"
  sudo apt-get update -qq
  sudo apt-get install -y docker-compose-plugin
fi

# --- Repository --------------------------------------------------------------------------

if [ ! -d "$REPO_DIR/.git" ]; then
  say "Cloning into $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"

# --- Configuration -----------------------------------------------------------------------

if [ ! -f .env ]; then
  cp infra/.env.example .env
  chmod 600 .env
  say "Created .env from the example"
  cat <<'EOF'
Fill it in before starting:

  nano ~/job-insight/.env

It needs DATABASE_URL (Neon), GEMINI_API_KEY, ADZUNA_APP_ID and ADZUNA_APP_KEY,
JSEARCH_API_KEY, and AIRFLOW_DB_PASSWORD (any long random string — it is only used
between the two containers). ALERT_WEBHOOK_URL is optional but worth setting: without
it a failure at 03:00 is recorded and nobody hears about it.

Then run this script again.
EOF
  exit 0
fi

chmod 600 .env

missing=()
for key in DATABASE_URL GEMINI_API_KEY AIRFLOW_DB_PASSWORD; do
  # Present and non-empty. Never print the value.
  if ! grep -qE "^${key}=.+" .env; then missing+=("$key"); fi
done

if [ ${#missing[@]} -gt 0 ]; then
  say "Not starting: .env is missing ${missing[*]}"
  echo "Fill them in with 'nano ~/job-insight/.env', then run this script again."
  exit 1
fi

# The mounted repository is written by the container (dbt's target/), so the container's
# user has to own it on Linux. On a laptop this does not matter; here it does.
if ! grep -q "^AIRFLOW_UID=" .env; then
  echo "AIRFLOW_UID=$(id -u)" >> .env
  say "Recorded AIRFLOW_UID=$(id -u) so the container can write to the repository"
fi

# --- Start -------------------------------------------------------------------------------

say "Building and starting"
docker compose -f infra/docker-compose.prod.yml up -d --build

say "Running"
docker compose -f infra/docker-compose.prod.yml ps

cat <<'EOF'

The Airflow UI is bound to localhost on the server and is not reachable from the internet.
Open a tunnel from your own machine:

    ssh -N -L 8080:localhost:8080 <user>@<server-ip>

then visit http://localhost:8080. The admin password is printed in the logs:

    docker compose -f infra/docker-compose.prod.yml logs airflow | grep -i password

All DAGs start paused. Unpause them in the UI once you have checked the connection:
db_healthcheck first, then ingest_ats, extract and transform.
EOF

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
RAW_URL="https://raw.githubusercontent.com/Seif-Douida/job-insight/main/infra/deploy/bootstrap.sh"

# Compose looks for `.env` beside the compose file; ours lives at the repository root,
# so every invocation has to say where it is. Defined once here for that reason.
COMPOSE="docker compose --env-file .env -f infra/docker-compose.prod.yml"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# `set -e` exits on the failing command and says nothing about it, which leaves a reader
# staring at an error from some tool they did not run. Every exit route out of this script
# should say what to do next, including the unplanned ones. Every step is safe to repeat.
on_exit() {
  local status=$?
  [ "$status" -eq 0 ] && return
  say "Stopped with exit status $status"
  echo "Nothing is half-installed that running it again will not fix:"
  if [ -d "$REPO_DIR/.git" ]; then
    echo "    bash $REPO_DIR/infra/deploy/bootstrap.sh"
  else
    echo "    curl -fsSL $RAW_URL | bash"
  fi
}
trap on_exit EXIT

# --- Docker ------------------------------------------------------------------------------

# A freshly booted Ubuntu cloud image spends its first few minutes running unattended
# upgrades, which hold the dpkg lock. Any install attempted during that window dies with
# "Could not get lock /var/lib/dpkg/lock-frontend", which reads like a broken script rather
# than a machine that is merely busy. Waiting is the whole fix.
wait_for_apt() {
  local waited=0
  while sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 ||
    pgrep -x apt >/dev/null || pgrep -x apt-get >/dev/null ||
    pgrep -x unattended-upgrade >/dev/null; do
    if [ "$waited" -eq 0 ]; then
      say "Waiting for Ubuntu's automatic updates to finish"
      echo "This is normal on a new machine and usually takes a minute or two."
    fi
    sleep 5
    waited=$((waited + 5))
    if [ "$waited" -ge 900 ]; then
      say "apt has been busy for 15 minutes, which is longer than it should be"
      echo "See what is holding it:  ps aux | grep -i -e apt -e unattended"
      exit 1
    fi
  done
}

if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker"
  wait_for_apt
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

if ! docker compose version >/dev/null 2>&1; then
  say "Installing the Docker Compose plugin"
  wait_for_apt
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

# The mounted repository is written by the container (dbt writes target/), so the container
# has to run as the user that owns these files. On a laptop any value works because Docker
# Desktop rewrites ownership; on Linux a wrong one means dbt cannot write and the transform
# DAG fails with a permission error that names nothing useful.
#
# The value is corrected rather than merely added, because the usual way to fill in .env on
# a server is to copy the one from a laptop, where it says 50000.
uid=$(id -u)
if ! grep -q "^AIRFLOW_UID=" .env; then
  echo "AIRFLOW_UID=$uid" >> .env
  say "Recorded AIRFLOW_UID=$uid so the container can write to the repository"
elif ! grep -q "^AIRFLOW_UID=$uid$" .env; then
  sed -i "s|^AIRFLOW_UID=.*|AIRFLOW_UID=$uid|" .env
  say "Corrected AIRFLOW_UID to $uid (this user owns the repository)"
fi

# --- Start -------------------------------------------------------------------------------

# Being added to the `docker` group does not affect the shell that is already open: group
# membership is fixed when a session starts. So the install above succeeds and the very next
# docker command fails with a permission error on the socket. The check is here rather than
# beside the install so that the repository and .env are already sorted out by the time
# anyone has to reconnect, and the second run goes straight through.
if ! docker info >/dev/null 2>&1; then
  say "Docker is installed, but this session cannot use it yet"
  cat <<EOF
Group membership is decided when a session starts, so the shell you are in now predates
being added to the 'docker' group. Disconnect and reconnect, then run this script again:

    exit
    ssh ubuntu@<server-ip>
    bash $REPO_DIR/infra/deploy/bootstrap.sh

Everything up to this point is done and will be skipped on the second run.
EOF
  exit 0
fi

say "Building and starting"
$COMPOSE up -d --build

say "Running"
$COMPOSE ps

say "Log in"
cat <<'EOF'
The Airflow UI is bound to localhost on the server and is not reachable from the internet.
Open a tunnel from your OWN machine, in its own terminal, and leave it running:

    ssh -N -L 8080:localhost:8080 <user>@<server-ip>

Then visit http://localhost:8080 and log in as 'admin'. Read the password HERE, on the
server:

    cd ~/job-insight && docker compose --env-file .env \
      -f infra/docker-compose.prod.yml exec airflow \
      cat /opt/airflow/simple_auth_manager_passwords.json.generated

All DAGs start paused, which is Airflow's default and looks identical to being stuck.
Unpause them in the UI one at a time, checking each before the next: db_healthcheck,
then ingest_ats, extract and transform.
EOF

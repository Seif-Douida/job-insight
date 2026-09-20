#!/usr/bin/env bash
#
# Pull the latest code and restart.  bash infra/deploy/update.sh
#
# The repository is mounted into the container, so most changes need only a restart. The
# image is rebuilt only when the dependency list or the Dockerfile has changed, which is
# the difference between a five-second update and a five-minute one on a small ARM box.

set -euo pipefail

cd "$(dirname "$0")/../.."

COMPOSE="docker compose -f infra/docker-compose.prod.yml"

before=$(git rev-parse HEAD)
git pull --ff-only
after=$(git rev-parse HEAD)

if [ "$before" = "$after" ]; then
  echo "Already up to date at ${after:0:8}."
  exit 0
fi

echo "Updated ${before:0:8} → ${after:0:8}"

if git diff --name-only "$before" "$after" | grep -qE '^(pyproject\.toml|infra/Dockerfile)$'; then
  echo "Dependencies changed, rebuilding the image."
  $COMPOSE up -d --build
else
  echo "Code only, restarting."
  $COMPOSE restart airflow
fi

$COMPOSE ps

# dbt's parse cache lives in the mounted repository and belongs to whichever dbt wrote it.
# The transform DAG already passes --no-partial-parse for that reason; clearing it here
# keeps a stale file from surviving an upgrade. See docs/lessons.md.
rm -f pipeline/dbt/target/partial_parse.msgpack

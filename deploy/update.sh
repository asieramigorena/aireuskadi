#!/usr/bin/env bash
# Keeps the Oracle VM at what the branch `pro` says, with nobody connecting to it. Every five minutes
# (deploy/aireuskadi-update.timer) it makes the folder of the repository a copy of `pro` and, when
# `pro` has a commit that was not deployed yet, deploys it:
#   - it pulls the images (all but the database: a new PostgreSQL can change the format of the data,
#     so that one is changed by hand);
#   - `docker compose up -d` recreates the containers whose image or settings changed, and runs
#     db-init first (the services wait for it), so a new migration is applied before the new code
#     that needs it. --remove-orphans removes the containers of services that left the compose;
#   - a container sees a new version of a file that it mounts from the repository (observability/,
#     tunnel/) only when it is created again, so the ones that mount a file that changed are;
#   - the images that nothing uses any more are deleted, or the disk of the VM fills up.
# The commit is written down only when all of that worked: a deployment that fails is tried again.
#
# It runs as root (installed in /usr/local/sbin, see aireuskadi-update.service): whoever can merge
# into pro can therefore run anything on the VM, which is why pro only takes reviewed pull requests.
# git runs as the owner of the folder: run by root it would leave files of root in it.
set -euo pipefail

REPO="${AIREUSKADI_REPO:-/home/ubuntu/aireuskadi}"
OWNER="${AIREUSKADI_REPO_OWNER:-ubuntu}"
# Written by aireuskadi.service when the VM starts (deploy/fetch-secrets.sh): until it is there the
# stack cannot be started, so there is nothing to do yet.
SECRETS="${AIREUSKADI_SECRETS:-/run/aireuskadi/secrets.env}"
# The last commit that was deployed (StateDirectory of the unit).
DEPLOYED="${AIREUSKADI_DEPLOYED:-/var/lib/aireuskadi/deployed}"
# The folders whose files the services mount from the repository.
MOUNTED=(observability tunnel)

if [ ! -f "$SECRETS" ]; then
  exit 0
fi

cd "$REPO"
as_owner() { runuser -u "$OWNER" -- "$@"; }
# A copy of pro: a file changed by hand in the folder would make a `git pull` fail every time. The
# .env is not in git, so it stays.
as_owner git fetch --quiet origin pro
as_owner git reset --hard --quiet origin/pro
head=$(as_owner git rev-parse HEAD)
before=$(cat "$DEPLOYED" 2>/dev/null || true)
if [ "$head" = "$before" ]; then
  exit 0
fi

compose=(docker compose --env-file .env --env-file "$SECRETS" -f docker-compose.prod.yml)
# Only the names: `config` without --services prints the compose with the secrets written in it.
names=$("${compose[@]}" config --services)
services=$(grep -vx postgres <<<"$names" || true)
# An empty list would make `pull` pull every image, the database too.
if [ -z "$services" ]; then
  echo "update: the compose file has no services but the database" >&2
  exit 1
fi
# shellcheck disable=SC2086 # one word per service, on purpose
"${compose[@]}" pull --quiet $services
"${compose[@]}" up -d --remove-orphans

# The mounted files changed since the last deployment (all of them the first time): the services
# that are running are created again. Only those: naming a stopped one would start it.
if [ -z "$before" ] || [ -n "$(as_owner git diff --name-only "$before" "$head" -- "${MOUNTED[@]}")" ]; then
  running=$("${compose[@]}" ps --services --status running)
  again=$(grep -xE 'grafana|alloy|loki|prometheus|tunnel' <<<"$running" || true)
  if [ -n "$again" ]; then
    # shellcheck disable=SC2086 # one word per service, on purpose
    "${compose[@]}" up -d --force-recreate --no-deps $again
  fi
fi

docker image prune --force
echo "$head" >"$DEPLOYED"

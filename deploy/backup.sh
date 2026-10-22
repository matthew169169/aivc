#!/usr/bin/env bash
# Consistent backup: stop the app before reading its persistent data volume.
set -euo pipefail
cd "$(dirname "$0")/.."
args=(--env-file deploy/cloud.env -f compose.yaml)
active=$(docker compose "${args[@]}" exec -T studio python -c 'import json; from urllib.request import urlopen; print(json.load(urlopen("http://127.0.0.1:8765/api/health"))["queue"]["active_jobs"])')
if [[ "$active" != "0" ]]; then
  echo 'Wait for active jobs to finish before making a consistent backup.' >&2
  exit 1
fi
mkdir -p deploy/backups
backup="deploy/backups/studio-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
docker compose "${args[@]}" stop studio
trap 'docker compose "${args[@]}" up -d studio' EXIT
docker compose "${args[@]}" run --rm --no-deps -T --entrypoint tar studio -C /data -czf - . > "$backup"
chmod 600 "$backup"
echo "Backup saved: $backup"

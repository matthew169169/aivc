#!/usr/bin/env bash
# Run on the Oracle VM after configuring deploy/cloud.env.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f deploy/cloud.env ]]; then
  echo 'Configure deploy/cloud.env from deploy/cloud.env.example first.' >&2
  exit 1
fi
export STUDIO_VERSION="$(git rev-parse HEAD)"
args=(--env-file deploy/cloud.env -f compose.yaml)
docker compose "${args[@]}" config --quiet
docker compose "${args[@]}" build --pull studio
docker compose "${args[@]}" pull gateway
docker compose "${args[@]}" up -d --wait --wait-timeout 300
docker compose "${args[@]}" exec -T studio python -c 'from urllib.request import urlopen; print(urlopen("http://127.0.0.1:8765/api/health").read().decode())'
echo 'Cloud deployment updated; the existing data volume was preserved.'

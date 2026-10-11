#!/bin/bash
# Expose this machine's Omics-GEM API publicly (temporary URL) for the
# GitHub Pages frontend. Keep this terminal + Mac awake while using it.
# For a permanent URL, deploy render.yaml on Render instead.
set -u
cd "$(dirname "$0")"
export OMICS_GEM_AUTH_ENABLED=false
export OMICS_GEM_ALLOWED_ORIGINS=https://matthew169169.github.io
nohup python3 run_local.py > /tmp/aivc_api.log 2>&1 &
echo "API: http://127.0.0.1:8765/api/health"
sleep 6
curl -s http://127.0.0.1:8765/api/health | head -c 80; echo
nohup cloudflared tunnel --url http://127.0.0.1:8765 --no-autoupdate > /tmp/aivc_tunnel.log 2>&1 &
sleep 12
URL=$(grep -o -E "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" /tmp/aivc_tunnel.log | head -n 1)
if [ -z "$URL" ]; then echo "tunnel not ready yet, see /tmp/aivc_tunnel.log"; exit 1; fi
echo "PUBLIC API: $URL/api/health"
echo "OPEN SITE:  https://matthew169169.github.io/aivc/?api=$URL"

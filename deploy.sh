#!/usr/bin/env bash
set -euo pipefail

VPS="vps"
REMOTE_DIR="~/mailwright"

echo "==> Syncing config files to $VPS:$REMOTE_DIR"
ssh "$VPS" "mkdir -p $REMOTE_DIR/data/owa_profile && sudo chown -R \$(whoami):\$(whoami) $REMOTE_DIR/data 2>/dev/null || true"
scp docker-compose.prod.yml Caddyfile .env "$VPS:$REMOTE_DIR/"

echo "==> Syncing OWA session"
scp data/owa_state.json "$VPS:$REMOTE_DIR/data/" 2>/dev/null || echo "  (no owa_state.json found, skipping)"
scp -r data/owa_profile/ "$VPS:$REMOTE_DIR/data/owa_profile/" 2>/dev/null || echo "  (no owa_profile found, skipping)"

echo "==> Pulling latest image and restarting on VPS"
ssh "$VPS" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d --remove-orphans"

echo "==> Done"

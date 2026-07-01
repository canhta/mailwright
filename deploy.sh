#!/usr/bin/env bash
set -euo pipefail

VPS="vps"
REMOTE_DIR="~/mailwright"

echo "==> Syncing config files to $VPS:$REMOTE_DIR"
ssh "$VPS" "mkdir -p $REMOTE_DIR/data && sudo chown -R \$(whoami):\$(whoami) $REMOTE_DIR/data 2>/dev/null || true"
scp docker-compose.yml .env "$VPS:$REMOTE_DIR/"

# If OWA_UPLOAD_URL is set in .env, `mailwright login` pushes the session
# straight to the running server over HTTP — nothing to scp, this is a no-op.
# This fallback only matters for the very first deploy, or if you're not
# using OWA_UPLOAD_URL.
echo "==> Syncing OWA session (fallback for first deploy / no OWA_UPLOAD_URL)"
scp data/owa_state.enc "$VPS:$REMOTE_DIR/data/" 2>/dev/null || echo "  (no data/owa_state.enc found, skipping)"

echo "==> Pulling latest image and restarting on VPS"
ssh "$VPS" "cd $REMOTE_DIR && docker compose pull && docker compose up -d --remove-orphans"

echo "==> Done"

#!/usr/bin/env bash
set -euo pipefail

VPS="vps"
REMOTE_DIR="~/mailwright"

echo "==> Syncing config files to $VPS:$REMOTE_DIR"
ssh "$VPS" "mkdir -p $REMOTE_DIR"
scp docker-compose.prod.yml Caddyfile .env "$VPS:$REMOTE_DIR/"

echo "==> Pulling latest image and restarting on VPS"
ssh "$VPS" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d --remove-orphans"

echo "==> Done"

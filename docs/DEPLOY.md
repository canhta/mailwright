# Deploy (VPS)

## Prerequisites
- A VPS with Docker + Docker Compose, and a domain A-record pointing at it.
- `data/owa_profile/` created on your laptop via `mailwright login` (M1) and a
  working `.env` (all `LLM_*`, `EMBED_*`, `JIRA_*`, `TELEGRAM_*`, `WEBHOOK_SECRET`,
  `STATUS_TARGETS`).

## Steps
1. Copy the repo to the VPS (git clone or rsync), set the domain in `Caddyfile`.
2. Copy your `.env` and the **`data/owa_profile/`** directory to the VPS repo root
   (`scp -r data/owa_profile user@vps:~/mailwright/data/`). `chmod -R 700 data`.
3. Build & start: `docker compose up -d --build`.
4. Check health: `curl -fsS https://<domain>/health` → `{"status":"ok"}`.
   Logs: `docker compose logs -f app`.
5. In Jira → Automation, point the *Send web request* action at
   `https://<domain>/jira/webhook` with header `X-Webhook-Secret: <WEBHOOK_SECRET>`
   and body `{"issue":"{{issue.key}}","status":"{{issue.status.name}}"}` (M5).
6. Verify end-to-end: a new Product mail produces a Telegram card/notice; approving
   creates the Jira ticket; moving it to Done replies in the thread + pings Telegram.

## Session refresh
When the OWA session expires, `poll` reports `OwaLoginRequired` (Telegram shows the
poll-failed warning). Re-run `mailwright login` on your laptop and re-copy
`data/owa_profile/` to the VPS, then `docker compose restart app`.

## Backups
Back up `data/app.db` regularly (e.g. nightly `sqlite3 data/app.db ".backup ..."`
to off-box storage). The OWA profile and `.env` are sensitive — store securely.

## Updates
`git pull && docker compose up -d --build`.

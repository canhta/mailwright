# Deploy (VPS)

`docker-compose.yml` binds the app to `127.0.0.1:8080` only — bring your own
reverse proxy (nginx, Caddy, whatever's already on the box) and point it
there for TLS.

## Prerequisites

- A VPS with Docker + Docker Compose, and a domain pointing at it through your
  reverse proxy.
- A working `.env` (all `LLM_*`, `EMBED_*`, `JIRA_*`, `TELEGRAM_*`,
  `WEBHOOK_SECRET`, `STATUS_TARGETS`). See [`SETUP.md`](SETUP.md).

## Steps

1. Set `OWA_UPLOAD_URL=https://<domain>/owa/session` and a random
   `OWA_UPLOAD_SECRET` in `.env` **before** your first `mailwright login` —
   this makes `login` push the session straight to the server over HTTP, so
   you never need to manually copy session files around, including on
   refresh.
2. Copy the repo to the VPS (git clone or rsync) and point your reverse proxy
   at `127.0.0.1:8080`.
3. `./deploy.sh` — syncs `docker-compose.yml` + `.env`, then pulls and
   restarts the container. (It also opportunistically scps
   `data/owa_state.enc` as a fallback for a first deploy before you've run
   `login` with `OWA_UPLOAD_URL` set — safe to ignore if that file doesn't
   exist yet.)
4. Run `mailwright login` on your laptop. With `OWA_UPLOAD_URL` configured,
   this pushes the session to the running server directly.
5. Check health: `curl -fsS https://<domain>/health` → `{"status":"ok"}`.
   Logs: `docker compose logs -f app`.
6. In Jira → Automation, point the *Send web request* action at
   `https://<domain>/jira/webhook` with header
   `X-Webhook-Secret: <WEBHOOK_SECRET>` and body
   `{"issue":"{{issue.key}}","status":"{{issue.status.name}}"}`.
7. Verify end-to-end: a new Product mail produces a Telegram card/notice;
   approving creates the Jira ticket; moving it to Done replies in the
   thread and pings Telegram.

## Session refresh

When the OWA session expires, `poll` reports `OwaLoginRequired` (Telegram
shows the poll-failed warning). Re-run `mailwright login` on your laptop —
with `OWA_UPLOAD_URL` set, that's the whole fix, no VPS access needed.
Without it, re-run `deploy.sh` to scp the refreshed `data/owa_state.enc`
across, then `docker compose restart app`.

## Backups

Back up `data/app.db` regularly (e.g. nightly
`sqlite3 data/app.db ".backup ..."` to off-box storage). `data/owa_state.enc`
and `.env` are sensitive — store securely; the state file is encrypted at
rest with `FERNET_KEY`, but `.env` (which holds that key) is not.

## Updates

`git pull && ./deploy.sh`

# Setup & Test Guide

Gets mailwright running end to end against your real Outlook/M365 mailbox,
in four stages: read mail (M1), file Jira tickets (M2), draft with an LLM
(M3), and run the full interactive Telegram agent (M4).

> **Why OWA instead of Microsoft Graph:** the Graph API path was blocked by
> the company tenant (app registration disabled; `Mail.*` consent requires
> admin). So mailwright drives Outlook Web (OWA) with Playwright instead —
> you sign in once in a real browser, and it reuses that session to call the
> Outlook REST API (`outlook.office.com/api/v2.0`). No admin involvement, no
> app registration.

Start with M1 below: confirm `login` works with your own account and that
`poll` returns candidate mails. Jira, LLM drafting, and the Telegram agent
build on top in M2–M4.

---

## 0. Prerequisites

- A machine **with a real browser** (your laptop) for the one-time login. **Google
  Chrome or Microsoft Edge installed** is strongly recommended — Microsoft login
  blocks Playwright's bundled Chromium more often. The VPS runs headless later
  using the saved session.
- **Python 3.12+** and **uv** (<https://docs.astral.sh/uv/getting-started/installation/>).

---

## 1. Install the project

```bash
uv sync                              # virtualenv + dependencies (incl. Playwright)
uv run playwright install chromium   # only needed if you have no Chrome/Edge
uv run pytest -q                     # sanity check: all unit tests pass
```

---

## 2. Configure `.env`

```bash
cp .env.example .env
```

Generate a key — it encrypts the OWA session file at rest, so it's needed
from the first login onward, not just for later milestones:

```bash
uv run python -c "from mailwright.crypto import generate_key; print(generate_key())"
```

Edit `.env` — note there is **no Azure/Graph app, no client ID, no tenant**:

```bash
# Outlook folder to scan. "Inbox" is the well-known inbox.
# If you route Product mails into a custom folder, use its folder id.
MAIL_FOLDER=Inbox

# Comma-separated. An entry WITH "@" matches that exact address;
# an entry WITHOUT "@" is a domain (matches anyone @that-domain).
# For a first smoke test, the company domain alone is fine.
SENDER_ALLOWLIST=product-team@example.com, example.com

COMPANY_DOMAIN=example.com

# Where your signed-in OWA session gets stored, encrypted with FERNET_KEY.
OWA_STATE_PATH=data/owa_state.enc

DB_PATH=data/app.db
FERNET_KEY=<paste the generated key here>
POLL_INTERVAL_SECONDS=180
```

> `.env` and `data/` are git-ignored — your session and secrets never get committed.

---

## 3. Log in (one-time, on your laptop)

```bash
uv run python -m mailwright.cli login
```

- A **real Chrome/Edge window opens** at Outlook Web.
- **Sign in with your COMPANY account** and complete MFA.
- Wait until your **inbox is fully loaded**, then return to the terminal and
  **press ENTER**.
- The terminal prints `Login complete; OWA session saved to data/owa_state.enc.`
  — that one encrypted file is your whole session; there's no profile
  directory to manage.

No consent prompt, no admin — it's a normal browser sign-in, exactly like opening
Outlook on the web.

---

## 4. Poll your mailbox

```bash
uv run python -m mailwright.cli poll
```

This launches a **headless** browser with the saved session, captures the OWA API
token, calls the Outlook REST API, and stores matching mails. Expected output:

```
Stored 2 new candidate mail(s):
  - <AAMkAGI2...@example.com>  New feature: CSV export for billing
  - <AAMkAGI3...@example.com>  Bug: login page 500 on mobile
```

- Run it again — already-seen mails are **deduplicated**, so a second run with no
  new mail prints `Stored 0 new candidate mail(s):`.
- Stored rows live in `data/app.db` (table `processed_mails`).

### Troubleshooting

| Symptom | Fix |
|---|---|
| `OwaLoginRequired: No OWA token captured ...` | The session expired or isn't valid headless — re-run `login`. |
| `Stored 0` but you expected mail | Check `SENDER_ALLOWLIST` matches the real senders; confirm the mails are recent and in `MAIL_FOLDER`. |
| Browser won't sign in / "not secure" | Install Chrome or Edge so the tool uses a real browser channel (not bundled Chromium). |
| Inspect the DB | `sqlite3 data/app.db "SELECT message_id, sender, subject FROM processed_mails;"` |

---

## 5. Deploy the session to the VPS (when ready)

Full deploy walkthrough is in [`DEPLOY.md`](DEPLOY.md). The short version:
set `OWA_UPLOAD_URL` in `.env` to the deployed server's `/owa/session`
endpoint, and `login` pushes the encrypted session straight there — no
manual file copying, on first deploy or any later re-login. When the
session eventually expires, the agent notices on the next poll and posts a
"please re-login" nudge to Telegram; re-running `login` on your laptop is
the whole fix.

> `data/owa_state.enc` is sensitive (it grants access to your mailbox) even
> though it's encrypted — keep `.env` (which holds the decryption key)
> private too, on both your laptop and the VPS.

---

## What success looks like (the M1 gate)

- [ ] `uv run pytest -q` → all pass.
- [ ] `login` completes in a normal browser sign-in — **no admin, no consent wall**.
- [ ] `poll` lists real candidate mails and deduplicates on a second run.

Once these pass, the biggest project risk (mailbox access) is retired and we
proceed to **M2 (Jira integration)**.

---

## M2 — Jira Integration

### 6. Create a Jira API token

1. Go to <https://id.atlassian.com/manage-profile/security/api-tokens>
2. Click **Create API token** → give it a name (e.g. `mailwright`) → copy it.

> The token is shown only once. Paste it into `.env` now before closing the dialog.

### 7. Add Jira credentials to `.env`

```bash
JIRA_BASE_URL=https://example.atlassian.net
JIRA_EMAIL=<your-atlassian-account-email, e.g. canh@example.com>
JIRA_API_TOKEN=<the token you just copied>
JIRA_PROJECT_KEY=<your Jira project key, e.g. PROD or SET>
```

> **How to find your project key:** open any Jira issue — the letters before the
> dash are the key (e.g. `PROD-123` → key is `PROD`).

### 8. Run the M2 smoke test

This creates one real ticket, adds a follow-up comment, and searches for duplicates:

```bash
uv run python - <<'PY'
import httpx
from mailwright.config import Settings
from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.jira.client import JiraClient
from mailwright.jira.models import TicketDraft
from mailwright.jira.ticket_service import TicketService
from mailwright.repositories.thread_ticket_map import ThreadTicketRepo

s = Settings()
conn = get_connection(s.db_path)
init_db(conn)
jira = JiraClient(s.jira_base_url, s.jira_email, s.jira_api_token, httpx.Client(timeout=30))
svc = TicketService(jira, ThreadTicketRepo(conn), s.jira_project_key)

d = TicketDraft(summary="[mailwright test] CSV export", description="Created by M2 manual verification.")
r1 = svc.create_or_comment("test-conv-m2", "<test-mid-1>", d)
print("created:", r1)
r2 = svc.create_or_comment("test-conv-m2", "<test-mid-2>", d)
print("follow-up:", r2)
print("duplicates:", svc.find_duplicates(d))
PY
```

**Expected output:**

```
created: TicketResult(key='PROD-42', url='https://example.atlassian.net/browse/PROD-42', created=True, commented=False)
follow-up: TicketResult(key='PROD-42', url='https://...', created=False, commented=True)
duplicates: [DuplicateCandidate(key='PROD-42', summary='[mailwright test] CSV export', ...)]
```

**After verifying:** delete the test issue in Jira (open the URL, `···` → Delete).

### Troubleshooting

| Symptom | Fix |
|---|---|
| `401 Unauthorized` | Wrong `JIRA_EMAIL` or `JIRA_API_TOKEN`. Token must belong to the account that owns the Jira site. |
| `404` on create | Wrong `JIRA_BASE_URL` (must end in `.atlassian.net`, no trailing slash). |
| `400 Bad Request` on create | Wrong `JIRA_PROJECT_KEY`. Check it matches exactly (case-sensitive). |
| `created=False` on first run | `test-conv-m2` already exists in `data/app.db` from a prior run. Change the conversation ID string or delete `data/app.db`. |
| `duplicates: []` | The just-created ticket hasn't been indexed yet — Jira's text search has a brief delay. Wait a few seconds and re-run only the `find_duplicates` line. |

---

## What success looks like (the M2 gate)

- [ ] `uv run pytest -q` → all pass.
- [ ] Smoke test prints `created=True` with a real Jira key and URL.
- [ ] Second call prints `commented=True` with the same key.
- [ ] The issue and its comment are visible in Jira.
- [ ] `duplicates` lists the just-created ticket.

Once these pass, M2 is complete and we proceed to **M3 (AI draft generation)**.

---

## M3 — LLM (AI Draft Generation)

### 9. Choose an LLM provider

The app uses any OpenAI-compatible endpoint. Add to `.env`:

**Option A — OpenAI (recommended for production)**

```bash
LLM_API_KEY=sk-...
LLM_BASE_URL=                      # leave empty → uses OpenAI
LLM_CLASSIFY_MODEL=gpt-4o-mini
LLM_DRAFT_MODEL=gpt-4o
LLM_STRUCTURED_MODE=json_schema
```

**Option B — DeepSeek (cheaper, good quality)**

```bash
LLM_API_KEY=sk-...                 # from platform.deepseek.com
LLM_BASE_URL=https://api.deepseek.com
LLM_CLASSIFY_MODEL=deepseek-chat
LLM_DRAFT_MODEL=deepseek-chat
LLM_STRUCTURED_MODE=json_object    # DeepSeek requires json_object, not json_schema
```

**Option C — Ollama (fully local)**

```bash
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_CLASSIFY_MODEL=llama3.1
LLM_DRAFT_MODEL=llama3.1
LLM_STRUCTURED_MODE=json_object
```

> **Note:** DeepSeek has no embeddings endpoint. If you use DeepSeek for the chat
> LLM, you must configure a **separate** embeddings provider (see M4 below).

### 10. Configure embeddings (required for memory)

Embeddings power the memory system: past ticket context, learned style, and NL
queries over your activity history. They use a **separate** endpoint from the chat LLM.

Add to `.env`:

**Option A — OpenAI embeddings**

```bash
EMBED_API_KEY=sk-...               # can be the same key as LLM_API_KEY
EMBED_BASE_URL=                    # leave empty → uses OpenAI
EMBED_MODEL=text-embedding-3-small
```

**Option B — Ollama local embeddings** (if you want fully offline)

```bash
EMBED_API_KEY=ollama
EMBED_BASE_URL=http://localhost:11434/v1
EMBED_MODEL=nomic-embed-text       # pull first: ollama pull nomic-embed-text
```

> If `EMBED_API_KEY` is left empty the app still starts, but any operation that
> writes or reads memory (feedback recording, NL queries, context injection) will
> fail at runtime with an authentication error.

### 11. Run the M3 smoke test

Runs `triage` — classifies and drafts tickets for all pending mails without
writing anything to Jira:

```bash
uv run python -m mailwright.cli triage
```

Expected output for each pending mail:

```
[IGNORED] Re: holiday schedule  (not a product request)
[DRAFT] Bug: login page 500 on mobile
  → summary: Login page returns 500 on mobile Safari
  → type: Bug
  → confidence: 0.92
```

If there are no pending mails yet, run `poll` first (step 4).

### Troubleshooting

| Symptom | Fix |
|---|---|
| `AuthenticationError` from LLM | Wrong `LLM_API_KEY` or `LLM_BASE_URL`. |
| `json.JSONDecodeError` / schema error | Model doesn't support the selected `LLM_STRUCTURED_MODE`. Switch to `json_object` for non-OpenAI providers. |
| `Stored 0` on triage | No pending mails. Run `poll` first. |
| Embeddings `AuthenticationError` | `EMBED_API_KEY` is empty or wrong. Set a valid key (see step 10). |

---

## What success looks like (the M3 gate)

- [ ] `triage` prints a DRAFT or IGNORED result for each pending mail.
- [ ] Draft summaries look reasonable for the mail content.

Once these pass, M3 is complete. Proceed to **M4 (Telegram bot)** for the full
interactive agent.

---

## M4 — Telegram Bot

The `agent` command needs a Telegram bot to send approval cards, answer NL
queries, and post daily summaries.

### 12. Create a bot via BotFather

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (name + username).
3. BotFather replies with your **bot token** — a string like
   `7123456789:AAF...`. Copy it.

```bash
TELEGRAM_BOT_TOKEN=7123456789:AAF...
```

### 13. Find your chat ID

1. Start a conversation with your new bot (click **Start**).
2. Send any message to it (e.g. `/start`).
3. Open this URL in your browser (replace `<TOKEN>` with your bot token):

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

4. Look for `"chat":{"id":` in the JSON response. That number is your chat ID.

```bash
TELEGRAM_CHAT_ID=123456789
```

> If `getUpdates` returns an empty `result` array, send another message to the
> bot and refresh.

### 14. Optionally restrict access

`TELEGRAM_ALLOWLIST` is a comma-separated list of numeric Telegram user IDs that
are allowed to interact with the bot. Leave it empty to allow any user who has
the bot link (fine for a private bot).

```bash
TELEGRAM_ALLOWLIST=123456789,987654321
```

> Your own user ID appears as `"from":{"id":...}` in the same `getUpdates`
> response from step 13.

### 15. Optionally configure the Jira status webhook

If you want the agent to post Jira ticket status changes back into the originating
mail thread and Telegram, set:

```bash
WEBHOOK_SECRET=any-random-string   # used to verify Jira webhook calls
WEBHOOK_PORT=8080
```

Then register a webhook in Jira (Project Settings → Webhooks) pointing at
`https://<your-host>/jira/webhook` with the `Issue updated` event. Skip this
for local testing.

### 16. Run the agent

```bash
uv run python -m mailwright.cli agent
```

Expected startup output:

```
INFO:     Started server process [...]
INFO:     Uvicorn running on http://0.0.0.0:8080
Bot started. Polling for updates...
```

Then in Telegram, send `/pending` to your bot — it should reply with any mails
awaiting approval (or "No pending approvals" if triage hasn't run yet).

### Troubleshooting

| Symptom | Fix |
|---|---|
| `telegram.error.InvalidToken` | `TELEGRAM_BOT_TOKEN` is wrong or has extra whitespace. |
| Bot starts but doesn't respond | You haven't sent `/start` to the bot yet, or `TELEGRAM_ALLOWLIST` excludes your user ID. |
| `TELEGRAM_CHAT_ID` not found | Make sure the bot received at least one message before calling `getUpdates`. |
| Webhook `422` from Jira | `WEBHOOK_SECRET` in `.env` doesn't match what you configured in Jira. |

---

## What success looks like (the M4 / full-agent gate)

- [ ] `agent` starts without errors.
- [ ] `/pending` in Telegram returns a response.
- [ ] After running `poll` + `triage`, approval cards appear in Telegram for
  mails that didn't meet the auto-create confidence threshold.
- [ ] Approving a card creates the Jira ticket and replies to the mail thread.

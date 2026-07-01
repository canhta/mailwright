# mailwright

**Turn your inbox into Jira tickets — automatically, with your judgment in the loop.**

mailwright watches your Outlook/M365 mailbox, reads incoming product mail with an
LLM, and drafts Jira tickets. High-confidence tickets it files for you; the rest it
sends to Telegram for one-tap approval. It links the ticket back into the email
thread, reports status changes, and **learns from every edit you make** so its
drafts sound more like you over time.

## Why it's different

- **No admin, no Azure app, no Graph API.** Corporate tenant blocking Mail API
  access? mailwright signs in through Outlook Web once in a real browser and reuses
  that session — exactly like you opening Outlook. Nothing to provision.
- **You stay in control.** Below a confidence threshold, nothing is filed without
  your approval. Approve, edit, or reject from your phone.
- **It gets better.** Every approval and edit teaches it your writing style and
  your team's rules. Ask it questions in plain language about what it's done.
- **Bring your own LLM.** Any OpenAI-compatible endpoint — OpenAI, DeepSeek, or a
  local Ollama. Run it fully self-hosted if you want.

## What it does

- 📥 Polls your mailbox, filters by sender allowlist, dedupes seen mail
- 🧠 Classifies requests, drafts a ticket (summary, type, priority, labels)
- 📎 Pulls in relevant attachments (PDF/DOCX/images) as ticket context
- 🎫 Auto-creates or comments on the right Jira issue per email thread
- 🔁 Searches for duplicates before filing
- 📲 Sends approval cards to Telegram; urgent mail gets escalated
- 🔗 Replies the ticket link into the original thread
- 🔔 Pushes Jira status changes back to the requester via a webhook
- 📊 Daily summary + nudges for stale approvals
- 🌙 Nightly reflection: learns your style, proposes rules you approve with `/rules`

## Quick start

Requires **Python 3.12+**, [uv](https://docs.astral.sh/uv/), and a real
Chrome/Edge for the one-time login.

```bash
uv sync
cp .env.example .env          # then fill in Jira / LLM / Telegram keys
uv run python -c "from mailwright.crypto import generate_key; print(generate_key())"  # -> FERNET_KEY

uv run python -m mailwright.cli login   # one-time browser sign-in (saves session)
uv run python -m mailwright.cli poll    # fetch mail and verify access
uv run python -m mailwright.cli agent   # run the full agent (bot + webhook + jobs)
```

`triage` does a dry classify/draft pass with no Jira writes if you want to watch it
think first. Full walkthrough in [`docs/SETUP.md`](docs/SETUP.md).

## Configuration

All config is environment variables (see [`.env.example`](.env.example)). The
essentials:

| Group | Keys |
|---|---|
| Mail | `SENDER_ALLOWLIST`, `COMPANY_DOMAIN`, `MAIL_FOLDER`, `POLL_INTERVAL_SECONDS` |
| Jira | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` |
| LLM | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_*_MODEL`, `CONFIDENCE_THRESHOLD` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ALLOWLIST` |
| Webhook | `WEBHOOK_SECRET`, `WEBHOOK_PORT`, `STATUS_TARGETS` |

`.env.example` includes ready-to-use presets for OpenAI, DeepSeek, and Ollama.

## How it works

```
OWA (Playwright session) ──token──> Outlook REST API
        │
   poll mail ──> classify ──> draft (with learned memory) ──> dedupe
        │                                                        │
   confident? ──yes──> create/comment Jira + upload + reply link
        └──no──> Telegram approval card ──> you approve/edit/reject
                                                        │
                          feedback ──> nightly reflection ──> style + rules
```

State is a single SQLite file. Every external service (OWA, Jira, LLM, Telegram)
is injected, so the pipeline is fully testable offline — run `uv run pytest -q`.

Package layout and design rationale are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md);
contributor setup and conventions are in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Deployment

A [`Dockerfile`](Dockerfile) builds on the Playwright image with browsers
preinstalled. Log in once locally, then either let `login` push the session
straight to your deployed server (`OWA_UPLOAD_URL`) or copy the encrypted
session file over yourself. Full walkthrough in [`docs/DEPLOY.md`](docs/DEPLOY.md).

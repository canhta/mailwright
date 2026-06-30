# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**mailwright** — a personal "mail → Jira" agent. It watches an Outlook/M365
mailbox, classifies incoming product mails with an LLM, drafts Jira tickets,
and either auto-creates them or asks for approval via Telegram. It learns from
your edits/approvals over time and answers natural-language questions about its
own activity.

**Key architectural constraint:** there is **no Microsoft Graph / Azure app**.
The company tenant blocked Graph, so mail access works by driving **Outlook Web
(OWA) with Playwright** — you sign in once in a real browser, and the tool
reuses that persistent profile to capture the bearer token OWA uses for its own
API calls, then talks to the **Outlook REST API** (`outlook.office.com/api/v2.0`)
directly. Zero admin. See `owa/session.py` and `docs/SETUP.md`.

## Commands

```bash
uv sync                              # create venv + install deps (incl. Playwright)
uv run playwright install chromium   # only if no system Chrome/Edge present
uv run pytest -q                     # run all tests (48 test files, no network)
uv run pytest tests/test_pipeline_service.py            # single file
uv run pytest tests/test_pipeline_service.py::test_name # single test
```

CLI entrypoint is `python -m mailwright.cli <command>`:

```bash
uv run python -m mailwright.cli login    # one-time HEADFUL browser login -> saves OWA profile
uv run python -m mailwright.cli poll     # headless: capture token, fetch+store new candidate mails
uv run python -m mailwright.cli triage   # dry-run classify/draft over pending mails (no Jira writes)
uv run python -m mailwright.cli agent    # long-running: Telegram bot + webhook + scheduled jobs
```

Generate the required `fernet_key`:
`uv run python -c "from mailwright.crypto import generate_key; print(generate_key())"`

There is no linter/formatter configured. Tests are the verification gate.

## Runtime architecture

`agent` is the real deployment. `telegram/bot.py::build_agent` is the **composition
root** — it constructs every collaborator and wires them together, then registers
handlers and scheduled jobs on a `python-telegram-bot` `Application`. `run_agent`
additionally serves a FastAPI webhook (uvicorn) in the same event loop.

Three concurrent surfaces inside `agent`:
- **Poll job** (every `poll_interval_seconds`): `MailPoller.poll()` → for each new
  `Message`, `PipelineService.process_message()` → send effects to Telegram.
- **Telegram handlers**: approval-card button callbacks (`telegram/dispatch.py` →
  `ApprovalService`), free-text → `AnswerService` (NL query) or pending-edit apply,
  `/pending`, `/rules`.
- **Jira webhook** (`webhook/app.py`): `POST /jira/webhook` (secret-checked) →
  `StatusReplyService` posts ticket status changes back to the originating mail
  thread and notifies Telegram. `GET /health` for liveness.

Daily jobs: morning summary, stale-approval nudge, and a 02:00 **reflection** run.

### The core pipeline (`pipeline/service.py::PipelineService.process_message`)

1. If the mail already references a Jira key (`brain/key_detector`) → mark
   `skip_has_ticket`, stop.
2. Classify (`brain/classifier`): not a ticket-worthy request → mark `ignore`.
3. Load attachments through an LLM relevance gate (`brain/attachment_gate` +
   `attachment_loader`); extract text/images (`ingest/extract`).
4. Build **memory context** (rules + learned style + similar past tickets + facts)
   and draft the ticket (`brain/drafter`).
5. Search Jira for duplicates (`TicketService.find_duplicates`).
6. **Confident** (`confidence >= threshold` AND issue type clear AND no duplicates)
   → create-or-comment the ticket, upload attachments, reply a link into the mail
   thread, record feedback. **Otherwise** → enqueue a pending approval and send an
   approval card to Telegram. Urgent mails get an extra escalation message.

`TicketService.create_or_comment` keys off `conversation_id` via `thread_ticket_map`:
the first mail in a thread creates an issue; later mails comment on it.

### Layers / packages

- `config.py` — `Settings` (pydantic-settings, loads `.env`). Comma-separated list
  envs (`sender_allowlist`, `telegram_allowlist`, `status_targets`) use
  `Annotated[list[str], NoDecode]` + a `field_validator`; without `NoDecode` pydantic
  tries to JSON-decode them and raises.
- `owa/` — `session` (Playwright token capture + caching/expiry, `OwaLoginRequired`),
  `rest_client` (Outlook REST), `replies` (post reply into a thread).
- `poller/mail_poller.py` — fetch + allowlist-filter + dedup into `processed_mails`.
- `brain/` — LLM-facing logic. `llm.py` builds an OpenAI-compatible **structured**
  client; `classifier`, `drafter`, `triage`, `attachment_gate`, `key_detector`,
  `schemas`.
- `jira/` — `client` (REST), `ticket_service` (create/comment/dedup), `adf` (Atlassian
  Document Format builder), `models`.
- `pipeline/` — orchestration services: `service` (main), `approval_service`,
  `answer_service` (NL Q&A over memory), `status_service`, `summary_service`,
  `nudge_service`, `reflection_service`, `replier`, `uploader`.
- `memory/` — learning substrate. `vector_store` (embeddings in SQLite),
  `embedder`, `context` (assembles draft context), `feedback` (records outcomes).
- `repositories/` — thin SQLite data-access objects, one per table.
- `telegram/` — `bot` (wiring + jobs), `dispatch`, `card`, `notifier`, `auth`, `markup`.
- `webhook/` — FastAPI `app` + `parse`.
- `db/` — `connection`, `schema` (single `SCHEMA_SQL`, idempotent `init_db`). All
  state is one SQLite file (`DB_PATH`, default `data/app.db`).

### The learning loop

`FeedbackRecorder` logs every created/approved/edited outcome to `episodic_log`
and `embeddings`. The nightly `ReflectionService` synthesizes a writing-style
profile (`StyleRepo`) and proposes rules (`RulebookRepo`, approved via
`/rules approve <id>`). `MemoryContext` injects active rules + style + nearest
past tickets/facts into future drafts. `AnswerService` answers free-text Telegram
questions over the same memory.

## LLM provider configuration

The OpenAI SDK is used as a **generic OpenAI-compatible client**. `LLM_BASE_URL`
empty → OpenAI; otherwise DeepSeek, Ollama, etc. `LLM_STRUCTURED_MODE` is
`json_schema` (OpenAI) or `json_object` (DeepSeek / older Ollama). Embeddings use
a **separate** endpoint (`EMBED_*`) because some chat providers (DeepSeek) have no
embeddings. See commented presets in `.env.example`.

## Testing conventions

`tests/conftest.py` disables `.env` loading (`autouse` fixture) so a populated
local `.env` can't leak into assertions. Tests are pure/offline — all external
collaborators (OWA, Jira, LLM, Telegram, Playwright) are injected, so seams are
constructor parameters. Preserve this: new code should take its dependencies as
arguments rather than constructing clients internally, matching `build_agent`.

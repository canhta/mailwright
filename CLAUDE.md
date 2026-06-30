# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**mailwright** — a personal "mail → Jira" agent. Watches an Outlook/M365 mailbox,
classifies incoming product mails with an LLM, drafts Jira tickets, auto-creates
or asks for approval via Telegram, and learns from edits/approvals over time.

**No Microsoft Graph / Azure app** — the tenant blocked it. Mail access works by
driving Outlook Web (OWA) with Playwright to capture its bearer token, then
calling the Outlook REST API directly. See `owa/session.py` + `owa/state_store.py`
for how the session is captured, encrypted, and persisted (locally or pushed to
a server via `login`).

## Commands

```bash
uv sync
uv run playwright install chromium   # only if no system Chrome/Edge
uv run pytest -q
uv run pytest tests/test_pipeline_service.py::test_name   # single test
uv run ruff check --fix src tests && uv run ruff format src tests
uv run mypy --config-file=pyproject.toml src
```

Pre-commit runs all three on every commit and may auto-fix/reformat — re-stage and re-commit if so.

CLI: `python -m mailwright.cli <login|poll|triage|agent>`. `agent` is the real
long-running deployment (Telegram bot + webhook + scheduled jobs).

Generate `fernet_key`: `uv run python -c "from mailwright.crypto import generate_key; print(generate_key())"`

## Runtime architecture

`telegram/bot.py::build_agent` is the composition root. Three concurrent surfaces:
- **Poll job** — heartbeat-driven (`poller/scheduling.py::should_poll_now`); interval
  and pause/resume are runtime-adjustable via Telegram (`/interval`, `/pause`, `/resume`),
  not a fixed scheduler interval.
- **Telegram handlers** — all commands register from one `_COMMANDS` list in `bot.py`
  (also drives `set_my_commands`); free text goes to `AnswerService` (tool-calling Q&A).
- **Jira webhook** (`webhook/app.py`) — ticket status updates and OWA session uploads,
  independently secret-checked.

Daily jobs: morning summary, stale-approval nudge, 02:00 reflection.

`pipeline/service.py::PipelineService.process_message` is the core pipeline: classify →
draft → dedup-check → confident mails auto-create/comment, uncertain ones queue for
Telegram approval. `TicketService.create_or_comment` keys off `conversation_id`: first
mail in a thread creates the issue, later ones comment on it.

### Layers

- `owa/` — token capture/caching + encrypted storage_state persistence
- `poller/` — fetch/allowlist/dedup, plus pure scheduling helpers
- `brain/` — LLM classify/draft/triage
- `jira/` — REST client, ticket create/comment/dedup, ADF builder
- `pipeline/` — orchestration (main pipeline, approvals, answers, status, summaries, nudges, reflection)
- `memory/` — embeddings + learning substrate (`episodic_log`, `RulebookRepo`, `StyleRepo`)
- `repositories/` — one thin SQLite repo per table
- `telegram/` — bot wiring/dispatch/formatting
- `webhook/` — FastAPI app
- `db/` — connection + schema, single SQLite file (`DB_PATH`)

`config.py`'s comma-separated list envs (`sender_allowlist`, `telegram_allowlist`,
`status_targets`) need `Annotated[list[str], NoDecode]` — without it pydantic tries
to JSON-decode them and raises.

## Adding tools to AnswerService

- Extend an existing tool's params before adding a new one; a new tool is only
  justified for a genuinely distinct operation (different resource, or read vs. mutate).
- Never fold a destructive action into a read tool behind a flag — give it its own tool.
- A mutating tool should reuse the same cleanup/side effects as the equivalent slash
  command, not reimplement them.
- Ground the system prompt in real capabilities (tools + the `_COMMANDS` list) so the
  LLM doesn't have to guess, or invent, what it can do.

## LLM provider configuration

Generic OpenAI-compatible client — `LLM_BASE_URL` empty means OpenAI, else
DeepSeek/Ollama/etc. Embeddings use a separate endpoint/config (some chat
providers have none). See `.env.example`.

## Testing conventions

Tests are pure/offline — every external collaborator is injected via constructor
params. `conftest.py` disables `.env` loading so a local `.env` can't leak into
assertions. New code should follow this: take dependencies as arguments, don't
construct clients internally.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**mailwright** — a personal "mail → Jira" agent. Watches an Outlook/M365 mailbox,
classifies incoming product mails with an LLM, drafts Jira tickets, auto-creates
or asks for approval via Telegram, and learns from edits/approvals over time.

## Architecture

The `agent` deployment runs three concurrent surfaces: a heartbeat-driven poll
job (interval/pause runtime-adjustable via Telegram), Telegram command and
free-text handlers (free text goes through tool-calling Q&A), and a Jira
webhook (status updates + OWA session uploads). The core pipeline classifies
each mail, drafts a ticket, checks for duplicates, then auto-creates or queues
it for Telegram approval.

Roughly layered into: OWA session handling, mail polling/scheduling, LLM
classify/draft/triage, Jira client + ticket service, pipeline orchestration,
the memory/learning substrate, one SQLite repo per table, and the Telegram/webhook glue.

## Commands

```bash
uv sync
uv run pytest -q
uv run pytest path/to/test.py::test_name   # single test
uv run ruff check --fix src tests && uv run ruff format src tests
uv run mypy --config-file=pyproject.toml src
```

Pre-commit runs the above on every commit and may auto-fix/reformat — re-stage and re-commit if so.

CLI: `python -m mailwright.cli <login|poll|triage|agent>`. `agent` is the real deployment.

## Gotchas

- No Microsoft Graph/Azure app — mail access drives Outlook Web with Playwright
  (`owa/`); see that package for the session capture/persistence flow.
- `config.py`'s comma-separated env lists (`sender_allowlist`, etc.) need
  `Annotated[list[str], NoDecode]`, or pydantic-settings tries to JSON-decode
  them and raises.
- `_COMMANDS` in `telegram/bot.py` is the single source of truth for Telegram
  commands (drives both handler registration and `set_my_commands`) — register
  new commands there, not as separate calls.
- `TicketService.create_or_comment` keys off `conversation_id`: first mail in a
  thread creates the Jira issue, later ones comment on it.

## Adding agent tools

Prefer extending an existing tool's params over adding a new one. Keep
destructive/mutating actions in their own tool, never behind a flag on a read
tool. Ground the system prompt in real capabilities (tools + `_COMMANDS`) so
the LLM doesn't invent limitations.

## Testing conventions

Tests are pure/offline — external collaborators are injected via constructor
params, never constructed internally. `conftest.py` disables `.env` loading so
a local `.env` can't leak into assertions.

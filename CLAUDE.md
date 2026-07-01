# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**mailwright** — a personal "mail → Jira" agent. Watches an Outlook/M365 mailbox,
classifies incoming product mails with an LLM, drafts Jira tickets, auto-creates
or asks for approval via Telegram, and learns from edits/approvals over time.

## Architecture

The `agent` deployment runs three concurrent surfaces: a heartbeat-driven poll
job (interval/pause runtime-adjustable via Telegram), Telegram command and
free-text handlers (free text goes through the tool-calling agent), and a Jira
webhook (status updates + OWA session uploads). The core pipeline classifies
each mail, drafts a ticket, checks for duplicates, then auto-creates or queues
it for Telegram approval.

Full package layout and layering rules live in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — read that before adding a new
package or moving code between layers. Short version: transport (`telegram/`,
`webhook/`, `owa/`, `jira/`) never sits below orchestration (`pipeline/`,
`agent/`); orchestration reaches transport-shaped behavior (rendering, auth
checks) through `pipeline/interfaces.py`, not direct imports.

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
- `COMMANDS` in `telegram/handlers.py` is the single source of truth for
  Telegram commands (drives both handler registration and `set_my_commands`)
  — register new commands there, not as separate calls.
- `TicketService.create_or_comment` keys off `conversation_id`: first mail in a
  thread creates the Jira issue, later ones comment on it.

## Adding agent tools

Add the schema + handler to the matching domain file under
`agent/tools/{jira,memory,mail}.py` (or a new domain file if none fits) — see
`docs/ARCHITECTURE.md` for why tools are split by domain rather than schema
vs. dispatch. Prefer extending an existing tool's params over adding a new
one. Keep destructive/mutating actions in their own tool, never behind a flag
on a read tool. Ground the system prompt in real capabilities (tools +
`COMMANDS`) so the LLM doesn't invent limitations. See `docs/TOOL_DESIGN.md`
for the fuller checklist (risk-tiering, ID-based targeting, description
boundaries, etc).

## Testing conventions

Tests are pure/offline — external collaborators are injected via constructor
params, never constructed internally. `conftest.py` disables `.env` loading so
a local `.env` can't leak into assertions.

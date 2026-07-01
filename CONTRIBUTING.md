# Contributing

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). See
[`docs/SETUP.md`](docs/SETUP.md) for the full environment walkthrough
(mailbox, Jira, Telegram, LLM keys).

```bash
uv sync
cp .env.example .env
uv run pre-commit install
```

## Before opening a PR

```bash
uv run pytest -q
uv run ruff check --fix src tests && uv run ruff format src tests
uv run mypy --config-file=pyproject.toml src
```

Pre-commit runs the same checks on every commit and may auto-fix/reformat —
re-stage and re-commit if it does.

## Conventions

- Tests are pure/offline: external collaborators (DB, HTTP clients, LLM) are
  injected via constructor params, never constructed inside the class under
  test. See existing `tests/` for the hand-written-fake pattern in use.
- Keep destructive/mutating actions in their own function or tool — never
  behind a flag on a read path. See [`docs/TOOL_DESIGN.md`](docs/TOOL_DESIGN.md)
  when adding a new agent tool.
- Follow the existing package layout described in
  [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — transport (`telegram/`,
  `webhook/`, `owa/`) stays separate from orchestration (`pipeline/`, `agent/`)
  and data access (`repositories/`).

## Commit messages

Short, imperative summary line; explain *why* in the body when it isn't
obvious from the diff. Keep commits focused — one logical change each.

# mailwright architecture & repo restructure

This documents the target package structure for mailwright and the rationale
behind it. It was produced as a design pass over the existing (already
reasonably sound) codebase, aimed at fixing specific coupling/duplication
problems rather than a ground-up rewrite.

Status: **approved and implemented** (see migration approach below for the
commit sequence). Only the OSS hygiene files were still pending as of this
writing.

## Goals

- Maintainable, well-designed structure — no specific prior pain points, just
  "make this hold up as the codebase grows."
- Fix concrete problems found in review, not theoretical ones.
- Stay proportionate to a single-deploy, personal-scale agent — not a
  multi-team OSS library. Full hexagonal architecture, Unit-of-Work, and a DI
  framework were evaluated and rejected as overkill (see "Out of scope").
- Cheap to make public later (LICENSE/CONTRIBUTING/CHANGELOG/SECURITY.md) if
  that decision is ever made, without a second restructuring pass.

## What's already right (kept as-is)

Research into comparable production Python service structures (FastAPI
production templates, the "Cosmic Python" / *Architecture Patterns with
Python* lineage) validates the existing top-level split: transport packages
(`telegram/`, `webhook/`, `owa/`) separate from orchestration (`pipeline/`)
separate from data access (`repositories/`). This is not changing.

Also validated as fine at this scale, **not changing**:
- One repository class per table in `repositories/`, raw SQL, no ORM/Unit-of-Work.
- A single flat `pydantic-settings` `Settings` class in `config.py`.
- Flat `tests/` mirroring `src/` by module, hand-written Fakes for collaborators.
- `db/`, `ingest/`, `jira/`, `memory/`, `owa/`, `poller/`, `webhook/` package boundaries and internal file names.

## Problems found

1. **Duplicated composition logic.** `telegram/bot.py::build_agent()` and
   `cli.py`'s `_build_*` functions each independently construct the same
   object graph (Settings → db connection → repos → clients → services).
2. **`telegram/bot.py` (477 lines) mixes three concerns**: DI wiring,
   Telegram-specific plumbing (handlers, job queue), and business logic
   inline in handlers — e.g. `_on_delete` directly calls
   `jira_client.delete_issue` + `episodic.delete_by_ref` +
   `vector_store.delete_by_ref` rather than delegating to a service.
3. **`pipeline/answer_service.py` (503 lines) mixes four concerns**: prompt
   text, ~220 lines of tool-schema definitions, a long if/elif tool-dispatch
   block, and response formatting, behind a loosely-typed 9-arg constructor.
   This is also, functionally, the only part of the codebase that's actually
   agentic (system prompt + tools + a dispatch loop) — everything else in
   `brain/` is single-shot structured-output calls, not an agent loop.
4. **Dependency-direction leak.** `pipeline/service.py`, `nudge_service.py`,
   `summary_service.py`, and `approval_service.py` import concrete
   `telegram/card.py`, `formatting.py`, `auth.py` — orchestration reaching
   into the transport layer to build presentation output.
5. **Misplaced file.** `brain/attachment_loader.py` is not an LLM task — it's
   an orchestrator coordinating `owa` (transport) + `attachment_gate` (LLM
   decision) + `ingest.extract` (parsing). It only lives in `brain/` because
   it was built alongside `attachment_gate.py`.
6. **Inconsistent naming inside `pipeline/`.** Most files are `*_service.py`;
   `service.py`, `replier.py`, and `uploader.py` break the pattern.
7. **No OSS hygiene files.** No LICENSE, CONTRIBUTING.md, CHANGELOG.md,
   SECURITY.md — fine while private, but the first blockers if ever made public.

## Target structure

```
src/mailwright/
  agent/            NEW — promoted out of pipeline/answer_service.py.
                     This is the actual agent: system prompt, tools, a
                     tool-calling dispatch loop. Promoted to a top-level
                     peer of pipeline/ rather than nested under it, since
                     telegram/ invokes it directly for free-text Q&A
                     (per CLAUDE.md) — it doesn't route through pipeline/.
    prompts.py         system message
    tools/             NEW subpackage — split by business domain, not by
                        schema-vs-dispatch. Each tool's JSON schema and its
                        handler are tightly coupled and change together, so
                        they're co-located per domain rather than spread
                        across one flat tools.py and one flat dispatch.py.
      jira.py            search_jira_jql, get_jira_issue, delete_jira_issue
                          — schema + handler for each, touches jira/
      memory.py          search_memory, get_recent_events, add_rule,
                          store_fact, list_memory, update_rule, forget_fact
                          — schema + handler for each, touches
                          memory/ + repositories/ (episodic, rulebook, vector_store)
      mail.py            send_email — schema + handler, touches owa/
      __init__.py        aggregates all domains into the single schema
                          list + name→handler registry agent/service.py
                          consumes (replacing the long if/elif)
    formatting.py      result rendering (e.g. _format_jql_results)
    service.py         thin orchestrator (was AnswerService); constructor
                        gets real concrete type annotations (JiraClient,
                        OutlookRestClient, RulebookRepo, etc.) replacing the
                        current untyped params — not Protocols; per "Out of
                        scope" below, full interface abstraction here isn't justified

  llm/              NEW — extracted from brain/llm.py + brain/schemas.py.
                     Shared LLM-client primitives: both tasks/ (single-shot
                     calls) and agent/ (tool-calling loop) depend on this,
                     so it doesn't belong inside either.
    client.py          StructuredLLM / ToolCallLLM / build_structured_llm
                        (was llm.py; renamed to match jira/client.py convention)
    schemas.py         structured-output types (unchanged content)

  tasks/            RENAMED from brain/, minus llm.py/schemas.py (moved to
                     llm/) and attachment_loader.py (moved to pipeline/).
                     What's left is genuinely single-shot LLM calls with no
                     tool loop — "tasks" is the standard term for this in
                     agentic-system codebases, as distinct from "agent".
    classifier.py, drafter.py, triage.py, attachment_gate.py, key_detector.py
    (unchanged content, only the package name changes)

  pipeline/         Orchestration use-cases. Suffixes normalized to
                     *_service.py; gains 2 files.
    message_service.py    (was service.py — process one incoming message)
    reply_service.py      (was replier.py)
    upload_service.py     (was uploader.py)
    attachment_loader.py  MOVED from brain/ — orchestrates owa + tasks +
                           ingest, not an LLM task itself
    deletion_service.py   NEW — extracted from telegram/bot.py's inline
                           _on_delete (Jira delete + episodic delete +
                           vector-store delete), now one reusable,
                           independently testable method
    interfaces.py         NEW — Protocols pipeline/ depends on
                           (ApprovalCardRenderer, AuthChecker, TextFormatter)
                           so pipeline/ stops importing telegram/ concretes.
                           telegram/card.py, auth.py, formatting.py keep
                           their concrete implementations and don't need to
                           import this file — Protocol satisfaction is
                           structural. container.py wires the concrete
                           telegram/ implementations into pipeline/
                           constructors.
    approval_service.py, nudge_service.py, reflection_service.py,
    status_service.py, summary_service.py   (unchanged)

  telegram/         bot.py shrinks to pure wiring; gains handlers.py.
    bot.py             Application factory, handler registration, job-queue
                        scheduling only — no business logic, no DI wiring
    handlers.py        NEW — command/callback bodies (/rules, /delete,
                        /poll, /interval, /pause, /resume, /status, /new,
                        /pending). Each delegates to a container-provided
                        service instead of calling repos/clients inline.
    auth.py, card.py, dispatch.py, formatting.py, markup.py, notifier.py
    (unchanged — these become the concrete Protocol implementations
    consumed via pipeline/interfaces.py)

  container.py      NEW — composition root for the full agent. AgentContainer
                     dataclass + build_container(settings, commands) ->
                     AgentContainer, constructing every concrete object the
                     agent needs exactly once: db connection, all repos,
                     llm/, jira/, owa/ clients, agent/, every pipeline/
                     service, poller/. telegram/bot.py::build_agent() calls
                     this instead of re-deriving the object graph inline.

                     cli.py's poll/triage commands deliberately do NOT route
                     through build_container() — they're intentionally
                     lightweight dry-run paths (see README/docs/SETUP.md)
                     that shouldn't require Jira/Telegram config just to
                     construct. The one concrete duplication found between
                     them (OwaSession -> OutlookRestClient construction) is
                     extracted as container.build_owa_client(settings),
                     shared by both build_container() and cli.py's
                     _build_poller() — fixing the actual duplication without
                     forcing the lightweight commands through the full graph.

  db/, ingest/, jira/, memory/, owa/, poller/, repositories/, webhook/
                     unchanged
  config.py, models.py, crypto.py, cli.py
                     unchanged
```

## OSS hygiene additions

Added now (cheap, no functional impact) so a future public-release decision
doesn't require a second pass:

- `LICENSE` — MIT.
- `CONTRIBUTING.md` — dev setup (point to README/docs/SETUP.md), commit
  conventions, pre-commit expectations (already enforced, just documented).
- `CHANGELOG.md` — Keep a Changelog format, starting at `[Unreleased]`.
- `SECURITY.md` — how to report a vulnerability.

Not added — genuinely only matter once public, and cost nothing to add later:
issue/PR templates, `py.typed` marker, CODEOWNERS.

## Out of scope (evaluated, rejected)

- **Full Protocol/interface layer for every repo and client.** Research
  (Cosmic Python lineage) explicitly warns against over-applying this in
  Python — duck typing plus the targeted `pipeline/interfaces.py` above
  already fixes the one real dependency-direction violation found. Repos are
  passed as concrete classes today and that's fine; nothing currently
  requires them to be swappable.
- **Unit-of-Work pattern across repositories.** Only pays for itself when
  multi-repository writes need atomicity. No such requirement was found.
- **Nested config groups** (`JiraSettings`, `TelegramSettings`, etc.). The
  research shows this is a supported pattern once a flat `Settings` class
  gets unwieldy, but at ~28 fields it's still within the range treated as
  fine. Revisit if it grows materially.
- **Restructuring `repositories/` or `tests/`.** Both already match what
  comparable codebases converge on at this scale.

## Migration approach

Big-bang: one branch, restructure fully, land together — not staged across
multiple deploys. Internally sequenced as separate commits for reviewability:

1. `container.py` composition root; `telegram/bot.py` switches to it, `cli.py`
   shares only `build_owa_client()`.
2. Extract `llm/` from `brain/llm.py` + `brain/schemas.py`.
3. Rename `brain/` → `tasks/` (remaining files).
4. Split `pipeline/answer_service.py` into `agent/` (new top-level package),
   with tools further split into `agent/tools/{jira,memory,mail}.py` by
   business domain.
5. Move `brain/attachment_loader.py` → `pipeline/attachment_loader.py`.
6. Normalize `pipeline/` file names (`message_service.py`, `reply_service.py`,
   `upload_service.py`).
7. Extract `pipeline/deletion_service.py` from `telegram/bot.py`'s `_on_delete`.
8. Split `telegram/bot.py` → thin `bot.py` + `handlers.py`.
9. Add `pipeline/interfaces.py`; fix the 4 pipeline→telegram concrete imports.
10. OSS hygiene files (LICENSE, CONTRIBUTING.md, CHANGELOG.md, SECURITY.md).

Every import path that changes (`brain.*` → `tasks.*`/`llm.*`,
`pipeline.answer_service` → `agent.service`, `pipeline.service` →
`pipeline.message_service`, etc.) needs a corresponding update across `src/`
and `tests/`, plus the two doc references in `docs/TOOL_DESIGN.md` that
mention `AnswerService`/`_TOOLS` by current path.

## Testing impact

No new testing strategy — hand-written Fakes for injected collaborators stays
the convention. Test files move/split to mirror the module moves above
(e.g. `tests/test_llm.py` imports update to `mailwright.llm.client`; new
`tests/test_container.py`, `tests/test_deletion_service.py`,
`tests/test_attachment_loader.py` (moved), `tests/agent/` mirroring the new
subpackage). Existing coverage is preserved, not expanded, except for the
newly-extracted `deletion_service.py` and `container.py` which need direct
tests since they didn't exist as isolated units before. `tests/test_answer_service.py`
splits along the same domain lines as `agent/tools/` (e.g.
`tests/agent/test_tools_jira.py`, `test_tools_memory.py`, `test_tools_mail.py`)
so each domain's schema/handler pair is tested next to its sibling, not in
one 500-line test file mirroring the old flat module.

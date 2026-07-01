# mailwright architecture

How mailwright's package structure is organized, and why.

## Layering

Three layers, each depending only downward:

- **Transport** (`telegram/`, `webhook/`, `owa/`, `jira/`) — talks to an
  external system (Telegram, Jira status webhook, Outlook Web, Jira's REST
  API). No business logic; just protocol/format translation.
- **Orchestration** (`pipeline/`, `agent/`) — use-cases that coordinate
  across transport, domain logic, and data access. `pipeline/` holds
  single-shot workflows (one file per use case); `agent/` is the tool-calling
  chat agent, promoted to a top-level peer of `pipeline/` because `telegram/`
  invokes it directly for free-text Q&A rather than routing through
  `pipeline/`.
- **Data access** (`repositories/`, `db/`) — one repository class per table,
  raw SQL, no ORM.

`tasks/` (single-shot structured-output LLM calls: classify, draft, triage,
attachment-gate) and `llm/` (the shared LLM-client primitives both `tasks/`
and `agent/` depend on) sit alongside orchestration as domain/LLM logic.

The rule that matters: **orchestration doesn't import transport concretes.**
Where `pipeline/` needs transport-shaped behavior (rendering an approval
card, checking Telegram auth, escaping HTML), it depends on a `Protocol` in
`pipeline/interfaces.py` rather than importing `telegram/*` directly. The
concrete telegram functions satisfy those Protocols structurally (no
inheritance needed) and get wired in at construction time.

## Package layout

```
src/mailwright/
  agent/              The tool-calling agent: system prompt, tools, dispatch
                       loop. Free-text Telegram Q&A goes straight here.
    prompts.py           system message
    tools/                split by business domain, not by schema-vs-dispatch
                          — each tool's JSON schema and handler change
                          together, so they're co-located per domain.
      jira.py               search_jira_jql, get_jira_issue, delete_jira_issue
      memory.py             search_memory, get_recent_events, add_rule,
                            store_fact, list_memory, update_rule, forget_fact
      mail.py               send_email
      __init__.py           aggregates all domains into one schema list +
                            name→handler registry
    formatting.py         result rendering (e.g. JQL search results)
    service.py            AnswerService — thin orchestrator over the above

  llm/                 Shared LLM-client primitives (StructuredLLM,
                       ToolCallLLM, structured-output schemas). Depended on
                       by both tasks/ and agent/, so it lives at their level
                       rather than inside either.

  tasks/                Single-shot LLM calls with no tool loop: classifier,
                       drafter, triage, attachment_gate, key_detector.

  pipeline/             Orchestration use-cases, one file per use case,
                       *_service.py suffix throughout:
    message_service.py    process one incoming message end to end
    approval_service.py, nudge_service.py, reflection_service.py,
    status_service.py, summary_service.py, reply_service.py,
    upload_service.py, deletion_service.py, attachment_loader.py
    interfaces.py          Protocols pipeline/ depends on for
                          transport-shaped behavior (see "Layering" above)

  telegram/             bot.py is pure wiring (Application factory, handler
                       registration, job-queue scheduling) — no business
                       logic. handlers.py holds every /command, callback,
                       and scheduled-job body, each delegating to a service.
                       auth.py, card.py, dispatch.py, formatting.py,
                       markup.py, notifier.py are the concrete
                       implementations satisfying pipeline/interfaces.py.

  container.py          Composition root for the full agent. AgentContainer
                       dataclass + build_container(settings, commands),
                       constructing every concrete object the agent needs
                       exactly once. telegram/bot.py::build_agent() calls
                       this rather than deriving the object graph inline.

                       cli.py's poll/triage commands deliberately do NOT
                       route through build_container() — they're
                       intentionally lightweight dry-run paths (see
                       docs/SETUP.md) that shouldn't require Jira/Telegram
                       config just to run. They share only
                       container.build_owa_client(settings).

  db/, ingest/, jira/, memory/, owa/, poller/, repositories/, webhook/
  config.py, models.py, crypto.py, cli.py
```

## Deliberately not done

Evaluated against comparable production Python service structures and
rejected as disproportionate for a single-deploy, personal-scale agent —
revisit if the scale assumptions change:

- **Protocols for every repo/client**, not just the transport boundary.
  Nothing currently requires repos to be swappable; `pipeline/interfaces.py`
  covers the one real dependency-direction problem that existed.
- **Unit-of-Work across repositories.** Only pays for itself when
  multi-repository writes need atomicity.
- **Nested config groups** in `config.py`. A flat `Settings` class is fine at
  its current size; worth nesting by concern (`jira__`, `telegram__`, ...) if
  it grows materially.
- **Full hexagonal/clean architecture** or a DI framework. Constructor
  injection plus the targeted Protocol boundary above gets the same
  testability without the ceremony.

## Conventions

- Tests are pure/offline: external collaborators are injected via
  constructor params and faked in tests, never constructed inside the class
  under test.
- New agent tools: see [`docs/TOOL_DESIGN.md`](TOOL_DESIGN.md) for the
  interface-design checklist, and add the schema + handler to the matching
  `agent/tools/{domain}.py` (or a new domain file if none fits).
- OSS hygiene files (`LICENSE`, `CONTRIBUTING.md`, `CHANGELOG.md`,
  `SECURITY.md`) exist at the repo root even though this stays a private,
  single-deploy project — cheap now, avoids a scramble if it's ever made
  public.

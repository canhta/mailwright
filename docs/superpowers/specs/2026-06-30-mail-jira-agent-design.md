# Mail → Jira Personal Agent — Design Spec

**Date:** 2026-06-30
**Author:** llm@seta-international.vn (with brainstorming assistant)
**Status:** Approved design — ready for implementation planning

---

## 1. Purpose & Context

The owner receives a high volume of email from the Product team requesting new
features / tickets. This project is a **single-user personal agent** that
automates the email → Jira workflow and, over time, **learns the owner's style
and preferences**. It is not a multi-tenant SaaS; everything is optimized for one
user, reliability, and low cost.

The agent has a "brain" (LLM reasoning + layered memory) but all side-effecting
I/O (creating Jira issues, sending email) is performed by **deterministic Python
code** with idempotency guarantees. The LLM's job is narrow: classify, draft,
decide.

Reference inspirations (architecture only, not drop-in): **OpenClaw**
(gateway → agent runtime, persistent memory, JSON allowlist config) and
**Hermes Agent / Nous Research** (layered memory, FTS5 history search, explicit
context compaction, learning over time).

---

## 2. Confirmed Decisions

| Topic | Decision |
|---|---|
| Email platform | **Microsoft 365 / Outlook** via **Microsoft Graph API**, delegated OAuth (personal login — owner's own mailbox). |
| Ticket creation autonomy | **Hybrid**: high confidence → auto-create; ambiguous → ask via Telegram. Threshold configurable. |
| Mail filtering | Two-tier cheap pre-filter: **Outlook folder/category + sender/domain allowlist**, then AI classification. |
| Jira | **Jira Cloud** (atlassian.net), REST API + API token. **One project**, project key in config. Issue type auto if clearly Bug/Task/Story, else ask. |
| Status detection | **Jira Cloud Automation → webhook** to a public HTTPS endpoint on the VPS (real-time). Fallback: polling if admin rights unavailable. |
| Agent channel | **Telegram bot** (inline buttons for Approve/Edit/Reject). |
| Daily summary | **Telegram**, 08:00 local. |
| Auto-reply recipients | **Reply-all within the original thread.** |
| Generated-content language | **English** (tickets, replies, summaries). |
| Programming language | **Python**. |
| Cost posture | **Balanced**: cheap model for classify/summary, stronger model for drafting tickets/replies. |
| Orchestration | **OpenAI Agents SDK** (tool-approval interrupts + SQLite sessions). |
| Telegram scope | **Groups + 1:1.** Approvals happen in group, but only allowlisted user IDs' taps count. |
| Authorization | **Allowlist of Telegram user IDs**; concrete IDs configured later. |
| Web UI | **Skipped in v1.** Telegram is the control surface; config via `.env`. Optional read-only dashboard is v2. |

---

## 3. Scope

### v1 — Core automations
1. **Auto-create Jira ticket** when a mail mentions a new task that has no existing
   ticket and references no Jira key — confidence-gated.
2. **Daily 08:00 summary** to Telegram.
3. **Auto-reply with ticket link** after creation (clearly marked as automated).
4. **Auto-reply with status** when a ticket transitions to **In Prod** or **Done**.

### v1 — Approved extensions
- **Group A (data quality):**
  - **Duplicate/related detection** — search Jira for similar issues before
    creating; link/comment instead of creating a duplicate.
  - **Thread follow-ups → comment on the existing ticket** rather than creating a
    new one.
  - **Clarification drafting** — for vague requests (missing acceptance
    criteria/priority), draft a reply asking the sender for the missing details
    (owner approves).
- **Group B (proactive / agentic):**
  - **Stalled-work nudges** — request not yet ticketed, or ticket idle N days →
    nudge owner on Telegram.
  - **Urgency/escalation detection** — urgent/angry tone → flag immediately
    (don't wait for the 08:00 summary).
- **NL-query over Telegram** — free-text questions over mail + Jira ("what did
  Product ask this week?", "status of billing tickets?", "draft a reply to
  Anna's last email"). Side effects are always approval-gated.

### Learning (v1)
The agent learns: ticket writing style, reply writing style, mail-importance
classification, project/people context, and explicit rules the owner gives.
**In-context learning only — no fine-tuning** at this scale.

### Deferred to v2
Ticket enrichment (auto acceptance criteria, labels, epic links, assignee
suggestion), weekly digest to Product team, weekly analytics for the owner,
Telegram voice-note input, one-time backlog import, read-only web dashboard.

---

## 4. Architecture

```
                        ┌──────────────── VPS (Docker) ────────────────┐
 Outlook (MS Graph) ──► │  Mail Poller ─► Mail Processor ─► Jira Client │ ──► Jira Cloud
        ▲               │   (delta/2-5')    (AI brain)      (idemp.)    │        │
        │ reply-all     │                      │                        │        │ Automation rule
        └───────────────│  Reply Sender ◄─ Decision/Approval            │        ▼
                        │       ▲              │                        │  Jira Webhook ──► /jira/webhook
   Telegram (you+group) │       │              ▼                        │     (FastAPI, HTTPS via Caddy)
        ◄──────────────►│   Gateway/Bot ◄─► Agent Brain (OpenAI Agents SDK)
                        │       │              │
                        │   Scheduler (APScheduler): poll · 08:00 summary · nightly reflection
                        │   Memory: Rulebook+Style (always-in-prompt) · Semantic (mem0/sqlite-vec)
                        │            Episodic log (FTS5) · Few-shot draft store · Thread↔Ticket map
                        │   State: SQLite (single file)
                        └─────────────────────────────────────────────────────────────────────────┘
```

### Components

1. **Gateway / Bot** — Telegram interface (1:1 and group). Handles chat,
   Approve/Edit/Reject callbacks, slash commands. In groups, responds only to
   @mention / reply-to-bot / slash command / button taps to control token cost.
   Button callbacks are verified against the user-ID allowlist.
2. **Mail Poller** — Microsoft Graph delta query on the configured folder,
   filtered by sender/domain allowlist, every 2–5 minutes. Dedup by
   `internetMessageId`.
3. **Mail Processor (AI brain)** — classify intent → detect existing Jira key
   (regex `KEY-\d+` in subject/body + thread-map lookup) → if new task with no
   ticket → duplicate search → draft (title/description/type/priority) using
   rulebook + style profile + few-shot examples → confidence gate.
4. **Jira Client** — create/read/comment issues; **idempotency key =
   hash(internetMessageId)**; duplicate search.
5. **Reply Sender** — reply-all in the original thread via Graph, content marked
   `[Auto]` / "(Automated message.)".
6. **Jira Webhook Receiver** — FastAPI HTTPS endpoint; verifies a shared secret;
   on In Prod / Done transition looks up the thread map and triggers a status
   reply + Telegram notice.
7. **Scheduler** — APScheduler: mail poll; 08:00 summary; nightly memory
   reflection.
8. **Memory subsystem** — see §6.
9. **State DB** — single SQLite file.

---

## 5. Data Flow (per feature)

- **(1) Auto-create ticket:** poll → candidate mail → AI classify intent + detect
  existing key → if new task and no ticket → **duplicate search** in Jira →
  draft → confidence gate:
  - **High** (clearly Bug/Task/Story): create (idempotent) → store thread map →
    trigger (3) → notify Telegram.
  - **Ambiguous**: Telegram approval card **[Approve] [Edit] [Reject]**. Each
    decision is a learning signal.
  - **Duplicate found**: propose linking/commenting instead (owner confirms).
- **(2) Daily 08:00 summary → Telegram:** since last summary — new request mails,
  pending approvals, tickets created (links), In Prod/Done changes in last 24h →
  AI composes concise English summary.
- **(3) Reply ticket link:** immediately after creation → reply-all in thread:
  "Ticket created: `<link>`. (Automated message.)"
- **(4) Status reply:** Jira Automation → POST `/jira/webhook` (verify secret) →
  thread-map lookup → reply-all with status + Telegram notice. Dedup so each
  `(ticket, status)` is notified once.
- **Thread follow-up:** subsequent mail in a mapped thread → add a **comment to
  the existing ticket**, not a new ticket.
- **Clarification:** vague request → draft a "please clarify" reply (approval-gated).
- **Nudge / escalation:** scheduler/processor detects stalled or urgent items →
  proactive Telegram push.
- **NL-query:** free text (or @mention in group) → agent brain with read tools
  (search mail, search Jira, search memory) answers; any side effect is
  approval-gated.

---

## 6. Memory & Learning

Separation of concerns is the core principle: **rules and style must be
deterministic (always in prompt)**; only the long tail of facts goes behind
similarity search.

- **Rulebook (procedural)** — JSON/Markdown in SQLite, **always injected** into
  the system prompt. Hard rules (e.g. "never auto-reply outside the company
  domain", "always ask before X"). Editable via `/rules`. The agent may
  **propose** new rules (from reflection) but the owner **confirms** — the agent
  does not silently add rules.
- **Style profile** — short natural-language description of the owner's ticket &
  reply style, **re-distilled nightly** from recent edits/approvals. Always in
  prompt.
- **Few-shot draft store** — embeddings of approved `(context → draft)` pairs;
  retrieve top-k similar when drafting (separate stores for ticket vs reply).
- **Semantic memory** — facts/preferences (project mappings, who owns what,
  abbreviations). Implementation: **mem0 (embedded library)** or **DIY
  sqlite-vec** — chosen at implementation time; both acceptable. OpenAI
  `text-embedding-3-small`.
- **Episodic log** — append-only record of every mail/decision/ticket/status/
  Telegram message, with **FTS5 full-text search** for NL-query and
  "already-handled?" checks.
- **Thread↔Ticket map** — source-of-truth table linking
  `conversationId`/`internetMessageId` ↔ Jira key, plus state flags (link
  replied?, statuses notified).

### Context compaction
Three-tier: keep the last ~6–10 turns verbatim + one rolling running summary +
durable facts extracted to long-term store **before** dropping turns. Trigger at
~70% of an ~8–12k-token working budget. Use **observation masking** for bulky
email/Jira tool outputs to cut cost. `/tokens` and `/compact` commands expose
this.

### Learning loop
- **Approve** → store positive few-shot example.
- **Edit** → store the diff (richest signal); nightly reflection updates the
  style profile and may propose a rulebook change.
- **Reject (+reason)** → store as a negative note.
Reflection runs nightly.

---

## 7. Telegram Interaction

- **Approval cards:** ticket draft shows title/type/priority/description +
  **[Approve] [Edit] [Reject]**. Edit → owner sends a corrected version → agent
  accepts and learns. Clarification mails and status-reply previews can be
  approval-gated too (configurable; high-confidence auto).
- **Proactive pushes:** escalation flags, stalled nudges, "ticket created"
  notices, status-change notices.
- **Commands:** `/summary`, `/rules`, `/pending`, `/status <KEY>`, `/tokens`,
  `/compact`, `/mute`, `/resume`.
- **NL-query:** free text (1:1) or @mention (group) → agent brain with tools.
- **Groups:** approvals occur in-group but only allowlisted user IDs' taps are
  honored; non-authorized taps get an ephemeral "not authorized" answer. Bot
  responds only to mention/reply/command/button to bound cost.

---

## 8. Data Model (SQLite)

- `processed_mails` (message_id PK, conversation_id, sender, received_at,
  classification, action, ticket_key)
- `thread_ticket_map` (conversation_id, ticket_key, link_replied,
  statuses_notified, created_at)
- `pending_approvals` (id, type[ticket|clarify|reply], payload, status,
  tg_msg_id, created_at)
- `episodic_log` (id, ts, type, ref, content) + FTS5 virtual table
- `memory_facts` (id, text, embedding, source, updated_at) — or delegated to mem0
- `rulebook` (id, kind[hard|soft], text, status[active|proposed], updated_at)
- `style_examples` (id, kind[ticket|reply], context, draft, embedding, created_at)
- `feedback_events` (id, ts, approval_id, decision[approve|edit|reject], before,
  after, reason)
- `chats` (chat_id, role[control|broadcast], type) + `allowlist` (user_id)
- `jira_status_seen` (ticket_key, status, ts) — dedup
- `sessions` — OpenAI Agents SDK SQLite session store

---

## 9. Reliability & Security

- **Idempotency:** `hash(internetMessageId)` as the Jira create key; check
  `thread_ticket_map` before creating → no duplicates even on retry/crash.
- **Webhook auth:** shared secret token; HTTPS only (Caddy auto-TLS); reject
  unverified requests.
- **Graph auth:** delegated OAuth (personal login), least scope
  (`Mail.Read`, `Mail.Send`, `Mail.ReadWrite`, `offline_access`); refresh tokens
  stored encrypted; automatic refresh.
- **Retry/backoff:** exponential backoff for Graph/Jira/OpenAI; each mail
  processed independently; failures isolated; dead-letter for repeated failures.
- **Guards:** hard rule "no auto-reply outside the company domain"; token/cost
  caps; observation masking; cheap model for classification.
- **Crash recovery:** all state in SQLite; on restart, resume pending approvals;
  scheduler jobs idempotent.

---

## 10. Deployment (VPS)

- **Docker Compose:** `gateway/bot`, `worker` (poller + scheduler), `webhook`
  (FastAPI); **Caddy** reverse proxy for auto-TLS on the webhook endpoint.
  (Processes may be consolidated; the webhook must be publicly reachable.)
- **Config (`.env`):** Graph (client id/secret/tenant), Jira (url/email/token/
  **project key**), OpenAI key, Telegram bot token + chat IDs + allowlist user
  IDs, webhook secret, poll interval, confidence thresholds, company domain.
- **Persistence:** SQLite on a Docker volume + periodic backup.
- **Setup doc (deliverable):** register Azure app for Graph; create Jira API
  token + Automation rule pointing to the VPS webhook URL; create the Telegram
  bot via BotFather and configure commands/privacy.

---

## 11. Testing (TDD)

- **Unit:** Jira-key regex, idempotency, thread mapping/dedup, allowlist
  authorization, reply formatting, compaction trigger, webhook parsing/auth.
- **Mocks:** Graph, Jira, OpenAI, Telegram all mocked.
- **Integration:** one end-to-end path — fake mail → approval → ticket creation
  (mocked externals).
- **Eval:** a small labeled set measuring classification accuracy
  (request-vs-not, needs-ticket, issue-type).

---

## 12. Open Items for Implementation Planning

- Final choice: mem0 vs DIY sqlite-vec for semantic memory.
- Process consolidation: how many containers (3 vs 1 + Caddy).
- Exact confidence thresholds and the issue-type auto/ask boundary (tune with the
  eval set).
- Concrete `.env` values (allowlist IDs, project key, folder name, company
  domain) — owner fills in.

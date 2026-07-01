# Tool Design for Mailwright Agents

Distilled from Anthropic's ["Building Effective Agents"](https://www.anthropic.com/engineering/building-effective-agents)
and OpenAI's ["A Practical Guide to Building Agents"](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf),
applied to `AnswerService._TOOLS` — the single tool-calling loop in
`src/mailwright/pipeline/answer_service.py` that backs Telegram free-text chat.

## Principles

1. **Design the tool interface like a UI for the model, not a wrapper around a function.**
   Put yourself in the model's shoes: does the description alone tell it when to
   call this vs. a neighboring tool, and what shape to pass?
2. **State boundaries against neighboring tools in the description.** "Use X for Y,
   not this" beats letting the model guess from two similar-sounding tools.
3. **Poka-yoke: make wrong calls structurally hard.** When a tool must target one
   specific stored row, require an ID from a prior read tool rather than fuzzy text
   matching (`list_memory` → `update_rule`/`forget_fact`, never "guess the rule text").
4. **Keep the input format close to natural text.** Avoid escaping or format ceremony
   the model wouldn't have seen naturally in training data.
5. **One mutating action per tool; never hide a mutation behind a flag on a read
   tool.** (Already in `CLAUDE.md`.)
6. **Risk-tier every mutating tool in its own description.** State read vs. write,
   reversible vs. irreversible, and blast radius. Irreversible tools (`forget_fact`,
   `delete_jira_issue`) must say so and tell the model to confirm ambiguity before
   calling. Reversible tools (e.g. `update_rule` status flips) should say so too —
   it changes how cautious the model needs to be.
7. **Don't multiply near-duplicate tools; consolidate before splitting.** Split
   only when overlap/similarity causes the model to pick the wrong tool, not
   just because the tool count is high.
8. **Keep a single agent as long as possible.** Only consider a manager/handoff
   multi-agent split if the tool list grows large *and* tools become genuinely
   domain-distinct (e.g. a separate Jira-admin agent) — not before.
9. **Test tool wording with varied example phrasing, not just code review.** If the
   model picks the wrong tool or wrong args, fix the description first.

## Applying this to mailwright specifically

- **Naming convention:** tool name prefixes signal read vs. write —
  `search_`/`get_`/`list_` are read-only; `add_`/`store_`/`update_`/`forget_`/
  `delete_`/`send_` mutate.
- **Return-shape convention:** mutating tools return a boolean outcome key named
  after the verb (`stored`, `updated`, `deleted`, `sent`) plus `error` on failure;
  read tools return the data directly (a list or dict). New tools should follow
  this unless there's a specific reason not to.
- **No staleness schema.** There's no migration runner in `src/mailwright/db/schema.py`
  beyond idempotent `CREATE TABLE IF NOT EXISTS` — don't add `updated_at`/`confidence`
  columns for staleness tracking. Handle staleness by having the model call
  `list_memory` then `update_rule`/`forget_fact` when the owner corrects something,
  not via new timestamp/versioning columns.

## Checklist for adding or editing a tool

- [ ] Does an existing tool's params already cover this? Extend instead of adding,
      if read-only.
- [ ] Is this mutating? Put it in its own tool, never as a flag on a read tool.
- [ ] Does the description state what *not* to use it for (boundary vs. neighboring
      tools)?
- [ ] Does the description state reversibility / risk level, if mutating?
- [ ] Does dispatch return the same `{verb_bool: True, ...}` /
      `{verb_bool: False, error: str}` shape as sibling tools?
- [ ] If it targets one stored row, does the model have a prior read tool to get
      its ID (no fuzzy targeting by text)?

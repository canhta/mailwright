import logging

from mailwright.brain.schemas import MemoryDecision
from mailwright.jira.models import TicketDraft

log = logging.getLogger(__name__)

_SYSTEM = (
    "You manage long-term memory for an AI mail→Jira agent. "
    "After each pipeline outcome, decide whether there is a durable behavioral pattern worth storing. "
    "Good insights: 'Auth-related emails from the teacherzone domain tend to be high-priority bugs', "
    "'Feature requests about scheduling always need acceptance criteria clarified before creating a ticket'. "
    "BAD — never store: specific ticket keys, exact ticket summaries, sender email addresses, "
    "or any fact that will become stale when tickets are deleted or edited. "
    "Skip if this outcome is routine and reveals nothing new. "
    "If action is 'skip', insight must be an empty string."
)


class MemoryManager:
    """LLM-gated memory: decides what behavioral patterns are worth remembering."""

    def __init__(self, episodic_repo, vector_store, embedder, structured_llm) -> None:
        self._episodic = episodic_repo
        self._vectors = vector_store
        self._embedder = embedder
        self._llm = structured_llm

    def on_outcome(
        self,
        event_type: str,
        email_summary: str,
        draft: TicketDraft | None,
        result: str,
    ) -> None:
        if draft and event_type in ("created", "approved", "edited"):
            text = (
                f"Email: {email_summary}\n"
                f"Ticket: {draft.summary} [{draft.issue_type}/{draft.priority or 'no priority'}]"
            )
            try:
                vec = self._embedder.embed([text])[0]
                self._vectors.add("fewshot", text, vec)
            except Exception:
                log.warning("memory: failed to store fewshot embedding", exc_info=True)

        recent = self._episodic.recent(limit=5)
        recent_text = "\n".join(f"- {e.content}" for e in recent) or "(none)"
        draft_line = (
            f"{draft.summary} [{draft.issue_type}/{draft.priority or 'no priority'}]"
            if draft
            else "(no draft)"
        )
        user = (
            f"Event: {event_type}\n"
            f"Email: {email_summary}\n"
            f"Draft: {draft_line}\n"
            f"Outcome: {result}\n\n"
            f"Recent memory:\n{recent_text}"
        )
        try:
            decision = self._llm.parse(_SYSTEM, user, MemoryDecision)
            if decision.action == "write" and decision.insight:
                self._episodic.add("insight", decision.insight)
                log.info("memory: stored insight — %s", decision.insight[:80])
        except Exception:
            log.warning("memory: LLM decision failed, skipping write", exc_info=True)

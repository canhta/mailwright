import logging
from dataclasses import dataclass

from mailwright.llm.schemas import TriageDecision
from mailwright.models import Message
from mailwright.tasks.key_detector import find_jira_keys
from mailwright.telegram.card import render_approval_card

log = logging.getLogger(__name__)

_TRIAGE_SYSTEM = (
    "You are the action router for a mail→Jira pipeline. "
    "Given the classification result, drafted ticket, drafter confidence, and any duplicate tickets found, "
    "decide the next action:\n"
    "- 'create': auto-create the Jira ticket (high confidence, clear issue type, no blocking duplicates)\n"
    "- 'queue_approval': send to the owner for review "
    "(low confidence, unclear type, or potential duplicates that need human judgement)\n"
    "- 'ignore': the classifier was wrong — this is not actually a ticket-worthy request\n"
    "- 'skip_duplicate': clearly a duplicate of an existing ticket — skip silently\n"
    "Also set is_urgent=true if the mail signals an outage, escalation, or angry tone."
)


@dataclass
class OutgoingMessage:
    text: str
    buttons: list[tuple[str, str]] | None = None
    approval_id: int | None = None


class PipelineService:
    def __init__(
        self,
        classifier,
        attachment_loader,
        drafter,
        ticket_service,
        uploader,
        approval_repo,
        processed_repo,
        threshold: float,
        replier=None,
        feedback=None,
        memory_context=None,
        triage_llm=None,
    ) -> None:
        self._classifier = classifier
        self._loader = attachment_loader
        self._drafter = drafter
        self._tickets = ticket_service
        self._uploader = uploader
        self._approvals = approval_repo
        self._processed = processed_repo
        self._threshold = threshold
        self._replier = replier
        self._feedback = feedback
        self._memory = memory_context
        self._triage_llm = triage_llm

    def _triage(self, c, outcome, duplicates) -> TriageDecision:
        if self._triage_llm:
            draft = outcome.draft
            dup_list = [f"{d.key}: {d.summary}" for d in duplicates] or ["none"]
            ctx = (
                f"Classification: is_request={c.is_request} needs_ticket={c.needs_ticket} "
                f"issue_type={c.issue_type} priority={c.priority} confidence={c.confidence:.2f}\n"
                f"Draft summary: {draft.summary!r}\n"
                f"Draft type: {draft.issue_type}\n"
                f"Drafter confidence: {outcome.confidence:.2f} (threshold={self._threshold})\n"
                f"Issue type clear: {outcome.issue_type_clear}\n"
                f"Duplicates found: {', '.join(dup_list)}"
            )
            try:
                return self._triage_llm.parse(_TRIAGE_SYSTEM, ctx, TriageDecision)  # type: ignore[no-any-return]
            except Exception:
                log.warning("triage_llm failed, falling back to rule-based", exc_info=True)

        # Rule-based fallback (original logic)
        confident = (
            outcome.confidence >= self._threshold and outcome.issue_type_clear and not duplicates
        )
        return TriageDecision(
            action="create" if confident else "queue_approval",
            reason="rule-based",
            is_urgent=c.is_urgent,
        )

    def process_message(self, message: Message) -> list[OutgoingMessage]:
        mid = message.internet_message_id
        log.info(
            "pipeline: processing mid=%s subject=%r sender=%s", mid, message.subject, message.sender
        )

        if find_jira_keys(f"{message.subject}\n{message.body}"):
            log.info("pipeline: skip — mail already references a Jira key")
            self._processed.set_action(mid, "skip_has_ticket")
            return []

        c = self._classifier.classify(message)
        log.info(
            "pipeline: classify → is_request=%s needs_ticket=%s is_urgent=%s confidence=%.2f",
            c.is_request,
            c.needs_ticket,
            c.is_urgent,
            getattr(c, "confidence", -1),
        )
        if not (c.is_request and c.needs_ticket):
            log.info("pipeline: ignore — not a ticket-worthy request")
            self._processed.set_action(mid, "ignore")
            return []

        loaded = self._loader.load(message)
        log.debug(
            "pipeline: loaded %d attachment text(s), %d image(s)",
            len(loaded.texts),
            len(loaded.images),
        )
        mem = self._memory.build(f"{message.subject}\n{message.body}") if self._memory else ""
        outcome = self._drafter.draft(message, loaded.texts, loaded.images, memory_context=mem)
        draft = outcome.draft
        log.info(
            "pipeline: draft → summary=%r type=%s confidence=%.2f issue_type_clear=%s",
            draft.summary,
            draft.issue_type,
            outcome.confidence,
            outcome.issue_type_clear,
        )
        duplicates = self._tickets.find_duplicates(draft)
        if duplicates:
            log.info(
                "pipeline: %d duplicate(s) found: %s", len(duplicates), [d.key for d in duplicates]
            )

        decision = self._triage(c, outcome, duplicates)
        log.info(
            "pipeline: triage → action=%s reason=%r is_urgent=%s",
            decision.action,
            decision.reason,
            decision.is_urgent,
        )

        email_summary = f"From: {message.sender}\nSubject: {message.subject}"

        if decision.action in ("ignore", "skip_duplicate"):
            self._processed.set_action(mid, decision.action)
            return []

        if decision.action == "create":
            res = self._tickets.create_or_comment(message.conversation_id, mid, draft)
            log.info(
                "pipeline: ticket %s %s → %s",
                res.key,
                "commented" if res.commented else "created",
                res.url,
            )
            self._uploader.upload_all(message.id, message.has_attachments, res.key)
            self._processed.set_action(mid, "created", res.key)
            if self._replier:
                self._replier.reply_link(message.conversation_id, message.id, res.key, res.url)
            if self._feedback:
                self._feedback.on_outcome("created", email_summary, draft, res.key)
            verb = "Commented on" if res.commented else "Auto-created"
            effects: list[OutgoingMessage] = [
                OutgoingMessage(f"✅ {verb} {res.key}: {res.url}\n{draft.summary}")
            ]
        else:  # queue_approval
            payload = {
                "draft": {
                    "summary": draft.summary,
                    "description": draft.description,
                    "issue_type": draft.issue_type,
                    "priority": draft.priority,
                    "labels": draft.labels,
                },
                "conversation_id": message.conversation_id,
                "message_id": mid,
                "owa_message_id": message.id,
                "has_attachments": message.has_attachments,
                "subject": message.subject,
                "sender": message.sender,
            }
            approval_id = self._approvals.add("ticket", payload)
            log.info("pipeline: queued pending approval id=%d", approval_id)
            self._processed.set_action(mid, "needs_approval")
            text, buttons = render_approval_card(approval_id, draft, outcome.confidence, duplicates)
            effects = [OutgoingMessage(text, buttons, approval_id)]

        if decision.is_urgent:
            log.warning("pipeline: URGENT mail from %s — %r", message.sender, message.subject)
            esc = OutgoingMessage(text=f"🚨 Urgent mail from {message.sender}: {message.subject}")
            return [esc, *effects]
        return effects

from dataclasses import dataclass

from mailwright.brain.key_detector import find_jira_keys
from mailwright.models import Message
from mailwright.telegram.card import render_approval_card


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

    def process_message(self, message: Message) -> list[OutgoingMessage]:
        mid = message.internet_message_id

        if find_jira_keys(f"{message.subject}\n{message.body}"):
            self._processed.set_action(mid, "skip_has_ticket")
            return []

        c = self._classifier.classify(message)
        if not (c.is_request and c.needs_ticket):
            self._processed.set_action(mid, "ignore")
            return []

        loaded = self._loader.load(message)
        mem = self._memory.build(f"{message.subject}\n{message.body}") if self._memory else ""
        outcome = self._drafter.draft(message, loaded.texts, loaded.images, memory_context=mem)
        draft = outcome.draft
        duplicates = self._tickets.find_duplicates(draft)

        confident = (
            outcome.confidence >= self._threshold and outcome.issue_type_clear and not duplicates
        )

        if confident:
            res = self._tickets.create_or_comment(message.conversation_id, mid, draft)
            self._uploader.upload_all(message.id, message.has_attachments, res.key)
            self._processed.set_action(mid, "created", res.key)
            if self._replier:
                self._replier.reply_link(message.conversation_id, message.id, res.key, res.url)
            if self._feedback:
                self._feedback.record_created(f"{message.subject}\n{message.body}", draft, res.key)
            verb = "Commented on" if res.commented else "Auto-created"
            effects = [OutgoingMessage(f"✅ {verb} {res.key}: {res.url}\n{draft.summary}")]
        else:
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
            }
            approval_id = self._approvals.add("ticket", payload)
            self._processed.set_action(mid, "needs_approval")
            text, buttons = render_approval_card(approval_id, draft, outcome.confidence, duplicates)
            effects = [OutgoingMessage(text, buttons, approval_id)]

        if c.is_urgent:
            esc = OutgoingMessage(text=f"🚨 Urgent mail from {message.sender}: {message.subject}")
            return [esc, *effects]
        return effects

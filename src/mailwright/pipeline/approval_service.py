from dataclasses import dataclass

from mailwright.jira.models import TicketDraft
from mailwright.telegram.auth import is_authorized


@dataclass
class DecisionOutcome:
    authorized: bool
    text: str
    edit_card: bool


class ApprovalService:
    def __init__(
        self,
        approval_repo,
        ticket_service,
        uploader,
        allowlist: list[int],
        replier=None,
        feedback=None,
    ) -> None:
        self._repo = approval_repo
        self._tickets = ticket_service
        self._uploader = uploader
        self._allowlist = allowlist
        self._replier = replier
        self._feedback = feedback

    def _draft_from(self, payload: dict) -> TicketDraft:
        d = payload["draft"]
        return TicketDraft(
            summary=d["summary"],
            description=d["description"],
            issue_type=d["issue_type"],
            priority=d.get("priority"),
            labels=d.get("labels"),
        )

    def _email_summary(self, payload: dict) -> str:
        sender = payload.get("sender", "")
        subject = payload.get("subject", "")
        return f"From: {sender}\nSubject: {subject}"

    def _create(self, payload: dict) -> tuple[str, str]:
        draft = self._draft_from(payload)
        owa_message_id = payload.get("owa_message_id")
        res = self._tickets.create_or_comment(
            payload["conversation_id"], payload["message_id"], draft, owa_message_id=owa_message_id
        )
        self._uploader.upload_all(owa_message_id, payload.get("has_attachments", False), res.key)
        if self._replier:
            self._replier.reply_link(payload["conversation_id"], owa_message_id, res.key, res.url)
        return res.key, f"✅ Created {res.key}: {res.url}"

    def decide(self, approval_id: int, action: str, user_id: int) -> DecisionOutcome:
        if not is_authorized(user_id, self._allowlist):
            return DecisionOutcome(False, "You are not authorized.", False)
        rec = self._repo.get(approval_id)
        if rec is None or rec.status != "pending":
            return DecisionOutcome(True, "This request is no longer pending.", False)

        if action == "approve":
            ticket_key, text = self._create(rec.payload)
            self._repo.set_status(approval_id, "approved")
            if self._feedback:
                self._feedback.on_outcome(
                    "approved",
                    self._email_summary(rec.payload),
                    self._draft_from(rec.payload),
                    ticket_key,
                )
            return DecisionOutcome(True, text, True)

        if action == "reject":
            self._repo.set_status(approval_id, "rejected")
            if self._feedback:
                self._feedback.on_outcome(
                    "rejected",
                    self._email_summary(rec.payload),
                    self._draft_from(rec.payload),
                    "rejected by owner",
                )
            return DecisionOutcome(True, "❌ Rejected.", True)

        if action == "edit":
            self._repo.set_status(approval_id, "awaiting_edit")
            return DecisionOutcome(
                True,
                "✏️ Send the corrected description as a normal message; "
                "I'll create the ticket with it.",
                True,
            )
        return DecisionOutcome(True, "Unknown action.", False)

    def apply_edit(self, approval_id: int, new_description: str, user_id: int) -> DecisionOutcome:
        if not is_authorized(user_id, self._allowlist):
            return DecisionOutcome(False, "You are not authorized.", False)
        rec = self._repo.get(approval_id)
        if rec is None or rec.status != "awaiting_edit":
            return DecisionOutcome(True, "Nothing awaiting edit.", False)
        payload = dict(rec.payload)
        payload["draft"] = {**payload["draft"], "description": new_description}
        self._repo.update_payload(approval_id, payload)
        ticket_key, text = self._create(payload)
        self._repo.set_status(approval_id, "approved")
        if self._feedback:
            self._feedback.on_outcome(
                "edited",
                self._email_summary(payload),
                self._draft_from(payload),
                ticket_key,
            )
        return DecisionOutcome(True, text, True)

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

    def _create(self, payload: dict) -> str:
        draft = self._draft_from(payload)
        owa_message_id = payload.get("owa_message_id")
        res = self._tickets.create_or_comment(
            payload["conversation_id"], payload["message_id"], draft, owa_message_id=owa_message_id
        )
        self._uploader.upload_all(owa_message_id, payload.get("has_attachments", False), res.key)
        if self._replier:
            self._replier.reply_link(payload["conversation_id"], owa_message_id, res.key, res.url)
        if self._feedback:
            self._feedback.record_created(payload.get("subject", ""), draft, res.key)
        return f"✅ Created {res.key}: {res.url}"

    def decide(self, approval_id: int, action: str, user_id: int) -> DecisionOutcome:
        if not is_authorized(user_id, self._allowlist):
            return DecisionOutcome(False, "You are not authorized.", False)
        rec = self._repo.get(approval_id)
        if rec is None or rec.status != "pending":
            return DecisionOutcome(True, "This request is no longer pending.", False)

        if action == "approve":
            text = self._create(rec.payload)
            self._repo.set_status(approval_id, "approved")
            return DecisionOutcome(True, text, True)
        if action == "reject":
            self._repo.set_status(approval_id, "rejected")
            if self._feedback:
                self._feedback.record_reject(rec.payload.get("subject", ""), "owner rejected draft")
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
        old_desc = rec.payload["draft"].get("description", "")
        payload = dict(rec.payload)
        payload["draft"] = {**payload["draft"], "description": new_description}
        self._repo.update_payload(approval_id, payload)
        if self._feedback:
            self._feedback.record_edit(payload.get("subject", ""), old_desc, new_description)
        text = self._create(payload)
        self._repo.set_status(approval_id, "approved")
        return DecisionOutcome(True, text, True)

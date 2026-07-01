from dataclasses import dataclass

from mailwright.jira.models import TicketDraft
from mailwright.llm.client import StructuredLLM
from mailwright.llm.schemas import Draft
from mailwright.models import Message

_SYSTEM = (
    "You write Jira tickets for an engineering team from an email request. "
    "Write in English. Produce a concise imperative summary (<=120 chars) and a "
    "clear description capturing the ask and any acceptance criteria mentioned. "
    "Pick issue_type (Bug/Task/Story) and priority, or 'Unclear' if you cannot "
    "tell. confidence is your certainty from 0 to 1."
)


@dataclass
class DraftOutcome:
    draft: TicketDraft
    confidence: float
    issue_type_clear: bool


class TicketDrafter:
    def __init__(self, llm: StructuredLLM) -> None:
        self._llm = llm

    def draft(
        self,
        message: Message,
        attachment_texts: list[str] | None = None,
        images: list[str] | None = None,
        memory_context: str = "",
    ) -> DraftOutcome:
        user = f"From: {message.sender}\nSubject: {message.subject}\n\n{message.body}"
        if attachment_texts:
            joined = "\n\n---\n\n".join(attachment_texts)
            user += f"\n\nAttachments (extracted text):\n{joined}"
        system = _SYSTEM
        if memory_context:
            system = f"{_SYSTEM}\n\nContext you have learned:\n{memory_context}"
        d = self._llm.parse(system, user, Draft, images=images)
        ticket = TicketDraft(
            summary=d.summary,
            description=d.description,
            issue_type=d.issue_type,
            priority=None if d.priority == "Unclear" else d.priority,
        )
        return DraftOutcome(
            draft=ticket,
            confidence=d.confidence,
            issue_type_clear=d.issue_type != "Unclear",
        )

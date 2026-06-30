from mailwright.brain.llm import StructuredLLM
from mailwright.brain.schemas import ReadDecision
from mailwright.models import AttachmentMeta

_SYSTEM = (
    "You decide whether reading email attachments is necessary to write a good "
    "Jira ticket, being cost-conscious. Only choose to read attachments when the "
    "email body is insufficient on its own or explicitly refers to an attachment "
    "(e.g. 'see attached spec/mockup'). Return the ids of attachments worth "
    "reading; return read=false with an empty list if the body already suffices."
)


class AttachmentGate:
    def __init__(self, llm: StructuredLLM) -> None:
        self._llm = llm

    def decide(self, subject: str, body: str, attachments: list[AttachmentMeta]) -> ReadDecision:
        if not attachments:
            return ReadDecision(read=False, attachment_ids=[], reason="no attachments")
        listing = "\n".join(
            f"- id={a.id} name={a.name} type={a.content_type} size={a.size}" for a in attachments
        )
        user = f"Subject: {subject}\n\nBody:\n{body}\n\nAttachments:\n{listing}"
        return self._llm.parse(_SYSTEM, user, ReadDecision)

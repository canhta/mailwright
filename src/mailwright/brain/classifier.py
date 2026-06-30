from mailwright.brain.llm import StructuredLLM
from mailwright.brain.schemas import Classification
from mailwright.models import Message

_SYSTEM = (
    "You triage internal emails for an engineering team. Decide whether an email "
    "is a request for new work that needs a Jira ticket. Respond in English. "
    "Set is_request=true only for genuine new feature/bug/task requests (not FYIs, "
    "meeting invites, newsletters, or replies that already reference a ticket). "
    "Set needs_ticket=true only when a new ticket should be created. Choose the "
    "issue_type and priority, or 'Unclear' if you cannot tell. confidence is your "
    "certainty from 0 to 1. "
    "Set is_urgent=true when the email conveys urgency, an outage, or an angry/escalation tone."
)


class MailClassifier:
    def __init__(self, llm: StructuredLLM) -> None:
        self._llm = llm

    def classify(self, message: Message) -> Classification:
        user = f"From: {message.sender}\nSubject: {message.subject}\n\n{message.body}"
        return self._llm.parse(_SYSTEM, user, Classification)

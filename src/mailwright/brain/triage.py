from dataclasses import dataclass

from mailwright.brain.key_detector import find_jira_keys
from mailwright.jira.models import TicketDraft
from mailwright.models import Message

SKIP_HAS_TICKET = "skip_has_ticket"
IGNORE = "ignore"
AUTO_CREATE = "auto_create"
NEEDS_APPROVAL = "needs_approval"


@dataclass
class TriageResult:
    action: str
    draft: TicketDraft | None
    confidence: float
    existing_keys: list[str]
    reason: str


class TriageService:
    def __init__(self, classifier, drafter, threshold: float) -> None:
        self._classifier = classifier
        self._drafter = drafter
        self._threshold = threshold

    def triage(self, message: Message) -> TriageResult:
        keys = find_jira_keys(f"{message.subject}\n{message.body}")
        if keys:
            return TriageResult(
                SKIP_HAS_TICKET, None, 1.0, keys, "mail already references a ticket"
            )

        c = self._classifier.classify(message)
        if not (c.is_request and c.needs_ticket):
            return TriageResult(IGNORE, None, c.confidence, [], c.reason)

        outcome = self._drafter.draft(message)
        confident = outcome.confidence >= self._threshold and outcome.issue_type_clear
        action = AUTO_CREATE if confident else NEEDS_APPROVAL
        return TriageResult(action, outcome.draft, outcome.confidence, [], c.reason)

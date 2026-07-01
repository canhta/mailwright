import logging
from dataclasses import dataclass

from mailwright.jira.models import TicketDraft
from mailwright.models import Message
from mailwright.tasks.key_detector import find_jira_keys

log = logging.getLogger(__name__)

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
        log.info("triage: subject=%r sender=%s", message.subject, message.sender)
        keys = find_jira_keys(f"{message.subject}\n{message.body}")
        if keys:
            log.info("triage: skip — already references %s", keys)
            return TriageResult(
                SKIP_HAS_TICKET, None, 1.0, keys, "mail already references a ticket"
            )

        c = self._classifier.classify(message)
        log.info(
            "triage: classify → is_request=%s needs_ticket=%s is_urgent=%s confidence=%.2f reason=%r",
            c.is_request,
            c.needs_ticket,
            c.is_urgent,
            c.confidence,
            c.reason,
        )
        if not (c.is_request and c.needs_ticket):
            log.info("triage: ignore — %s", c.reason)
            return TriageResult(IGNORE, None, c.confidence, [], c.reason)

        outcome = self._drafter.draft(message)
        log.info(
            "triage: draft → summary=%r type=%s confidence=%.2f issue_type_clear=%s",
            outcome.draft.summary,
            outcome.draft.issue_type,
            outcome.confidence,
            outcome.issue_type_clear,
        )
        confident = outcome.confidence >= self._threshold and outcome.issue_type_clear
        action = AUTO_CREATE if confident else NEEDS_APPROVAL
        log.info("triage: action=%s (threshold=%.2f)", action, self._threshold)
        return TriageResult(action, outcome.draft, outcome.confidence, [], c.reason)

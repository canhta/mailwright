import logging
import time
from typing import cast

from mailwright.jira.models import DuplicateCandidate, TicketDraft, TicketResult
from mailwright.repositories.thread_ticket_map import PENDING_KEY, ThreadTicket, ThreadTicketRepo

log = logging.getLogger(__name__)


class TicketCreationInProgress(RuntimeError):
    """Another process claimed this conversation and hasn't finished creating its ticket."""


class TicketService:
    def __init__(
        self,
        jira,
        repo: ThreadTicketRepo,
        project_key: str,
        claim_wait_attempts: int = 6,
        claim_wait_seconds: float = 0.4,
    ) -> None:
        self._jira = jira
        self._repo = repo
        self._project_key = project_key
        self._claim_wait_attempts = claim_wait_attempts
        self._claim_wait_seconds = claim_wait_seconds

    def create_or_comment(
        self,
        conversation_id: str,
        source_message_id: str,
        draft: TicketDraft,
        owa_message_id: str | None = None,
    ) -> TicketResult:
        existing = self._repo.get(conversation_id)

        if existing is None and self._repo.try_claim(conversation_id):
            try:
                log.info(
                    "jira: creating issue project=%s summary=%r",
                    self._project_key,
                    draft.summary,
                )
                ref = self._jira.create_issue(self._project_key, draft)
            except Exception:
                self._repo.release_claim(conversation_id)
                raise
            log.info("jira: created %s → %s", ref.key, ref.url)
            self._repo.finalize_claim(conversation_id, ref.key, source_message_id, owa_message_id)
            return TicketResult(key=ref.key, url=ref.url, created=True, commented=False)

        # Either a ticket already exists, or another process won the claim
        # race between our GET and our own try_claim — wait for it to
        # finish rather than creating a duplicate.
        existing = self._wait_for_claim(conversation_id, existing)

        log.info(
            "jira: adding comment to existing ticket %s (conv=%s)",
            existing.ticket_key,
            conversation_id,
        )
        self._jira.add_comment(
            existing.ticket_key,
            f"Follow-up from email thread:\n\n{draft.description}",
        )
        return TicketResult(
            key=existing.ticket_key,
            url=self._jira.issue_url(existing.ticket_key),
            created=False,
            commented=True,
        )

    def _wait_for_claim(self, conversation_id: str, existing: ThreadTicket | None) -> ThreadTicket:
        for _ in range(self._claim_wait_attempts):
            existing = existing or self._repo.get(conversation_id)
            if existing is not None and existing.ticket_key != PENDING_KEY:
                return existing
            time.sleep(self._claim_wait_seconds)
            existing = self._repo.get(conversation_id)
        if existing is None or existing.ticket_key == PENDING_KEY:
            raise TicketCreationInProgress(
                f"ticket creation still in progress elsewhere for conversation {conversation_id}"
            )
        return existing

    def find_duplicates(self, draft: TicketDraft) -> list[DuplicateCandidate]:
        terms = draft.summary.replace('"', " ").strip()
        jql = f'project = "{self._project_key}" AND statusCategory != Done AND text ~ "{terms}"'
        return cast(list[DuplicateCandidate], self._jira.search_issues(jql))

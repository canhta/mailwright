import logging
from typing import cast

from mailwright.jira.models import DuplicateCandidate, TicketDraft, TicketResult
from mailwright.repositories.thread_ticket_map import ThreadTicketRepo

log = logging.getLogger(__name__)


class TicketService:
    def __init__(self, jira, repo: ThreadTicketRepo, project_key: str) -> None:
        self._jira = jira
        self._repo = repo
        self._project_key = project_key

    def create_or_comment(
        self,
        conversation_id: str,
        source_message_id: str,
        draft: TicketDraft,
        owa_message_id: str | None = None,
    ) -> TicketResult:
        existing = self._repo.get(conversation_id)
        if existing is not None:
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

        log.info("jira: creating issue project=%s summary=%r", self._project_key, draft.summary)
        ref = self._jira.create_issue(self._project_key, draft)
        log.info("jira: created %s → %s", ref.key, ref.url)
        self._repo.add(conversation_id, ref.key, source_message_id, owa_message_id)
        return TicketResult(key=ref.key, url=ref.url, created=True, commented=False)

    def find_duplicates(self, draft: TicketDraft) -> list[DuplicateCandidate]:
        terms = draft.summary.replace('"', " ").strip()
        jql = f'project = "{self._project_key}" AND statusCategory != Done AND text ~ "{terms}"'
        return cast(list[DuplicateCandidate], self._jira.search_issues(jql))

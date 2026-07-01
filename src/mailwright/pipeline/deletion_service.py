import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class DeleteOutcome:
    key: str
    deleted: bool
    error: str | None = None


class DeletionService:
    """Deletes a Jira issue and cleans up its associated memory (episodic log + vector store)."""

    def __init__(self, jira_client, episodic_repo, vector_store) -> None:
        self._jira = jira_client
        self._episodic = episodic_repo
        self._vectors = vector_store

    def delete(self, key: str) -> DeleteOutcome:
        key = key.upper().strip()
        try:
            self._jira.delete_issue(key)
            ep_removed = self._episodic.delete_by_ref(key)
            vs_removed = self._vectors.delete_by_ref(key)
            log.info("delete: removed %s (episodic=%d, vectors=%d)", key, ep_removed, vs_removed)
            return DeleteOutcome(key=key, deleted=True)
        except Exception as exc:
            log.warning("delete: failed to remove %s: %s", key, exc)
            return DeleteOutcome(key=key, deleted=False, error=str(exc))

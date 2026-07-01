from typing import Protocol

from mailwright.jira.models import DuplicateCandidate, TicketDraft


class ApprovalCardRenderer(Protocol):
    def __call__(
        self,
        approval_id: int,
        draft: TicketDraft,
        confidence: float,
        duplicates: list[DuplicateCandidate],
    ) -> tuple[str, list[tuple[str, str]]]: ...


class AuthChecker(Protocol):
    def __call__(self, user_id: int, allowlist: list[int]) -> bool: ...


class TextFormatter(Protocol):
    def __call__(self, text: str) -> str: ...

from dataclasses import dataclass


@dataclass
class TicketDraft:
    summary: str
    description: str
    issue_type: str = "Task"
    priority: str | None = None
    labels: list[str] | None = None


@dataclass
class JiraIssueRef:
    key: str
    url: str


@dataclass
class DuplicateCandidate:
    key: str
    summary: str
    status: str
    url: str


@dataclass
class TicketResult:
    key: str
    url: str
    created: bool
    commented: bool

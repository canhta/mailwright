from mailwright.jira.models import (
    DuplicateCandidate,
    JiraIssueRef,
    TicketDraft,
    TicketResult,
)


def test_ticket_draft_defaults():
    d = TicketDraft(summary="Add export", description="Please add CSV export")
    assert d.issue_type == "Task"
    assert d.priority is None
    assert d.labels is None


def test_value_objects():
    assert JiraIssueRef("PROD-1", "u").key == "PROD-1"
    assert DuplicateCandidate("PROD-2", "s", "Open", "u").status == "Open"
    assert TicketResult("PROD-1", "u", created=True, commented=False).created is True

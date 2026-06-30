from datetime import datetime

from mailwright.pipeline.summary_service import SummaryService
from mailwright.repositories.approvals import ApprovalRecord
from mailwright.repositories.processed_mails import ProcessedMail
from mailwright.repositories.status_events import StatusEvent


class FakeProcessed:
    def __init__(self, created):
        self._created = created

    def list_by_action_since(self, action, since):
        return self._created if action == "created" else []


class FakeApprovals:
    def __init__(self, pending):
        self._p = pending

    def list_pending(self):
        return self._p


class FakeStatus:
    def __init__(self, events):
        self._e = events

    def list_since(self, since):
        return self._e


def test_build_summary_contains_sections():
    processed = FakeProcessed(
        [
            ProcessedMail(
                message_id="<a>", subject="CSV export", ticket_key="PROD-7", action="created"
            )
        ]
    )
    approvals = FakeApprovals(
        [ApprovalRecord(1, "ticket", {"draft": {"summary": "Vague ask"}}, "pending")]
    )
    status = FakeStatus([StatusEvent("PROD-3", "Done", "2026-06-29 09:00:00")])
    svc = SummaryService(processed, approvals, status, window_hours=24)

    msg = svc.build(datetime(2026, 6, 30, 8, 0, 0))
    text = msg.text
    assert "PROD-7" in text and "CSV export" in text  # created
    assert "Vague ask" in text  # pending approval
    assert "PROD-3" in text and "Done" in text  # status change


def test_empty_summary_says_none():
    svc = SummaryService(FakeProcessed([]), FakeApprovals([]), FakeStatus([]), 24)
    text = svc.build(datetime(2026, 6, 30, 8, 0, 0)).text
    assert "none" in text.lower()

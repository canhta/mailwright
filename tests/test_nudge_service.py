from datetime import datetime

from mailwright.pipeline.nudge_service import NudgeService
from mailwright.repositories.approvals import ApprovalRecord


class FakeApprovals:
    def __init__(self, stale):
        self._stale = stale
        self.cutoff = None

    def list_pending_older_than(self, cutoff):
        self.cutoff = cutoff
        return self._stale


def test_nudge_lists_stale_and_computes_cutoff():
    appr = FakeApprovals(
        [ApprovalRecord(2, "ticket", {"draft": {"summary": "Old ask"}}, "pending")]
    )
    msg = NudgeService(appr, stale_days=3).build(datetime(2026, 6, 30, 8, 0, 0))
    assert msg is not None and "Old ask" in msg.text and "#2" in msg.text
    assert appr.cutoff == "2026-06-27 08:00:00"  # now - 3 days


def test_no_nudge_when_nothing_stale():
    assert NudgeService(FakeApprovals([]), 3).build(datetime(2026, 6, 30, 8, 0, 0)) is None

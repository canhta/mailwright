from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.jira.models import TicketResult
from mailwright.pipeline.approval_service import ApprovalService
from mailwright.repositories.approvals import ApprovalRepo
from mailwright.telegram.auth import is_authorized


class FakeTicketService:
    def __init__(self):
        self.created = []

    def create_or_comment(self, conv, mid, draft, owa_message_id=None):
        self.created.append((conv, mid, draft))
        return TicketResult("PROD-9", "https://x/PROD-9", created=True, commented=False)


class FakeUploader:
    def __init__(self):
        self.calls = []

    def upload_all(self, owa_id, has, key):
        self.calls.append(key)
        return 0


def _payload():
    return {
        "draft": {
            "summary": "s",
            "description": "d",
            "issue_type": "Story",
            "priority": "High",
            "labels": None,
        },
        "conversation_id": "conv-1",
        "message_id": "<m>",
        "owa_message_id": "owa-1",
        "has_attachments": True,
        "subject": "s",
    }


def _svc(tmp_path, allowlist=(111,)):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    repo = ApprovalRepo(conn)
    ts = FakeTicketService()
    up = FakeUploader()
    svc = ApprovalService(repo, ts, up, list(allowlist), auth_check=is_authorized)
    return svc, repo, ts, up


def test_unauthorized_user_blocked(tmp_path):
    svc, repo, ts, _ = _svc(tmp_path)
    aid = repo.add("ticket", _payload())
    out = svc.decide(aid, "approve", user_id=999)
    assert out.authorized is False and out.edit_card is False
    assert ts.created == []  # nothing created


def test_approve_creates_and_uploads(tmp_path):
    svc, repo, ts, up = _svc(tmp_path)
    aid = repo.add("ticket", _payload())
    out = svc.decide(aid, "approve", user_id=111)
    assert out.authorized and out.edit_card
    assert "PROD-9" in out.text
    assert len(ts.created) == 1 and up.calls == ["PROD-9"]
    assert repo.get(aid).status == "approved"


def test_reject_marks_rejected(tmp_path):
    svc, repo, ts, _ = _svc(tmp_path)
    aid = repo.add("ticket", _payload())
    out = svc.decide(aid, "reject", user_id=111)
    assert out.edit_card and "eject" in out.text
    assert repo.get(aid).status == "rejected" and ts.created == []


def test_edit_then_apply_edit_creates_with_new_description(tmp_path):
    svc, repo, ts, _ = _svc(tmp_path)
    aid = repo.add("ticket", _payload())
    svc.decide(aid, "edit", user_id=111)
    assert repo.get(aid).status == "awaiting_edit"
    out = svc.apply_edit(aid, "corrected description", user_id=111)
    assert out.authorized and "PROD-9" in out.text
    assert ts.created[0][2].description == "corrected description"
    assert repo.get(aid).status == "approved"


def test_decide_on_non_pending_is_noop(tmp_path):
    svc, repo, ts, _ = _svc(tmp_path)
    aid = repo.add("ticket", _payload(), status="approved")
    out = svc.decide(aid, "approve", user_id=111)
    assert out.authorized and out.edit_card is False
    assert ts.created == []


class FakeMemoryManager:
    def __init__(self):
        self.outcomes: list[tuple[str, str]] = []

    def on_outcome(self, event_type, email_summary, draft, result):
        self.outcomes.append((event_type, str(result)))


def test_memory_called_on_approve_edit_reject(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    repo = ApprovalRepo(conn)
    ts = FakeTicketService()
    up = FakeUploader()
    mgr = FakeMemoryManager()
    svc = ApprovalService(repo, ts, up, [111], auth_check=is_authorized, feedback=mgr)

    # approve → on_outcome("approved", ...)
    aid = repo.add("ticket", _payload())
    svc.decide(aid, "approve", 111)
    assert any(ev == "approved" and "PROD-9" in res for ev, res in mgr.outcomes)

    # reject → on_outcome("rejected", ...)
    aid2 = repo.add("ticket", _payload())
    svc.decide(aid2, "reject", 111)
    assert any(ev == "rejected" for ev, _ in mgr.outcomes)

    # edit → on_outcome("edited", ...)
    aid3 = repo.add("ticket", _payload())
    svc.decide(aid3, "edit", 111)
    svc.apply_edit(aid3, "new desc", 111)
    assert any(ev == "edited" for ev, _ in mgr.outcomes)


def test_unknown_action_returns_not_edit_card(tmp_path):
    svc, repo, ts, _ = _svc(tmp_path)
    aid = repo.add("ticket", _payload())
    out = svc.decide(aid, "frobnicate", user_id=111)
    assert out.authorized is True and out.edit_card is False
    assert ts.created == []

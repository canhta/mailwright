from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.jira.models import TicketResult
from mailwright.pipeline.approval_service import ApprovalService
from mailwright.repositories.approvals import ApprovalRepo


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
    svc = ApprovalService(repo, ts, up, list(allowlist))
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


class FakeFeedback:
    def __init__(self):
        self.created = []
        self.rejected = []
        self.edited = []

    def record_created(self, ctx, draft, key):
        self.created.append(key)

    def record_reject(self, ctx, reason):
        self.rejected.append(reason)

    def record_edit(self, ctx, old, new):
        self.edited.append((old, new))


def test_feedback_called_on_approve_edit_reject(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    repo = ApprovalRepo(conn)
    ts = FakeTicketService()
    up = FakeUploader()
    fb = FakeFeedback()
    svc = ApprovalService(repo, ts, up, [111], feedback=fb)

    # approve → record_created
    aid = repo.add("ticket", _payload())
    svc.decide(aid, "approve", 111)
    assert fb.created == ["PROD-9"]

    # reject → record_reject
    aid2 = repo.add("ticket", _payload())
    svc.decide(aid2, "reject", 111)
    assert fb.rejected

    # edit → record_edit
    aid3 = repo.add("ticket", _payload())
    svc.decide(aid3, "edit", 111)
    svc.apply_edit(aid3, "new desc", 111)
    assert fb.edited == [("d", "new desc")]


def test_unknown_action_returns_not_edit_card(tmp_path):
    svc, repo, ts, _ = _svc(tmp_path)
    aid = repo.add("ticket", _payload())
    out = svc.decide(aid, "frobnicate", user_id=111)
    assert out.authorized is True and out.edit_card is False
    assert ts.created == []

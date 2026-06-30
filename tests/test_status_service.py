from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.pipeline.status_service import StatusReplyService
from mailwright.repositories.thread_ticket_map import ThreadTicketRepo
from mailwright.webhook.parse import WebhookEvent


class FakeOwa:
    def __init__(self):
        self.replies = []

    def reply_all(self, mid, comment):
        self.replies.append((mid, comment))


def _setup(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    repo = ThreadTicketRepo(conn)
    repo.add("conv-1", "PROD-7", source_message_id="<m>", owa_message_id="owa-1")
    owa = FakeOwa()
    svc = StatusReplyService(owa, repo, ["In Prod", "Done"], "https://x")
    return svc, repo, owa


def test_status_reply_sends_and_dedups(tmp_path):
    svc, repo, owa = _setup(tmp_path)
    out = svc.handle(WebhookEvent("PROD-7", "Done"))
    assert out is not None and "PROD-7" in out.text
    assert len(owa.replies) == 1
    assert repo.get("conv-1").statuses_notified == ["Done"]
    # dedup: same status again → no send, no message
    assert svc.handle(WebhookEvent("PROD-7", "Done")) is None
    assert len(owa.replies) == 1


def test_ignores_non_target_status_and_unknown_key(tmp_path):
    svc, _, owa = _setup(tmp_path)
    assert svc.handle(WebhookEvent("PROD-7", "In Review")) is None
    assert svc.handle(WebhookEvent("NOPE-1", "Done")) is None
    assert owa.replies == []


def test_records_status_event_when_repo_provided(tmp_path):
    from mailwright.db.connection import get_connection
    from mailwright.db.schema import init_db
    from mailwright.repositories.status_events import StatusEventRepo

    svc, repo, _ = _setup(tmp_path)
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    event_repo = StatusEventRepo(conn)
    svc._status_event_repo = event_repo
    svc.handle(WebhookEvent("PROD-7", "Done"))
    events = event_repo.list_since("2000-01-01 00:00:00")
    assert len(events) == 1 and events[0].ticket_key == "PROD-7" and events[0].status == "Done"

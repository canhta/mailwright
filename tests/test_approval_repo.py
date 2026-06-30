from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.approvals import ApprovalRecord, ApprovalRepo


def _repo(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return ApprovalRepo(conn)


def test_add_get_roundtrip(tmp_path):
    repo = _repo(tmp_path)
    aid = repo.add("ticket", {"draft": {"summary": "s"}, "conversation_id": "c"})
    rec = repo.get(aid)
    assert isinstance(rec, ApprovalRecord)
    assert rec.kind == "ticket"
    assert rec.payload["draft"]["summary"] == "s"
    assert rec.status == "pending"
    assert rec.tg_message_id is None


def test_list_pending_and_set_status(tmp_path):
    repo = _repo(tmp_path)
    a = repo.add("ticket", {})
    b = repo.add("ticket", {})
    repo.set_status(a, "approved")
    pending = repo.list_pending()
    assert [r.id for r in pending] == [b]


def test_set_tg_message_id_and_update_payload(tmp_path):
    repo = _repo(tmp_path)
    aid = repo.add("ticket", {"draft": {"summary": "old"}})
    repo.set_tg_message_id(aid, 555)
    repo.update_payload(aid, {"draft": {"summary": "new"}})
    rec = repo.get(aid)
    assert rec.tg_message_id == 555
    assert rec.payload["draft"]["summary"] == "new"


def test_list_pending_older_than(tmp_path):
    repo = _repo(tmp_path)
    repo.conn.execute(
        "INSERT INTO pending_approvals (kind, payload, status, created_at) VALUES "
        "('ticket','{}','pending','2026-06-01 00:00:00'),"
        "('ticket','{}','pending','2026-06-29 00:00:00')"
    )
    repo.conn.commit()
    stale = repo.list_pending_older_than("2026-06-15 00:00:00")
    assert len(stale) == 1

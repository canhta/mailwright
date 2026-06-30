from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.processed_mails import ProcessedMail, ProcessedMailRepo


def _repo(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return ProcessedMailRepo(conn)


def test_add_and_exists(tmp_path):
    repo = _repo(tmp_path)
    assert repo.exists("<mid-1>") is False

    repo.add(
        ProcessedMail(
            message_id="<mid-1>",
            sender="a@x.com",
            subject="Hi",
            classification="candidate",
            action="pending",
        )
    )

    assert repo.exists("<mid-1>") is True


def test_get_returns_row(tmp_path):
    repo = _repo(tmp_path)
    repo.add(ProcessedMail(message_id="<mid-2>", sender="b@y.com", subject="New task"))

    got = repo.get("<mid-2>")
    assert got is not None
    assert got.sender == "b@y.com"
    assert got.subject == "New task"


def test_add_is_idempotent_on_duplicate(tmp_path):
    repo = _repo(tmp_path)
    repo.add(ProcessedMail(message_id="<dup>", sender="a@x.com"))
    repo.add(ProcessedMail(message_id="<dup>", sender="a@x.com"))  # must not raise
    assert repo.exists("<dup>") is True


def test_stores_and_reads_body_and_has_attachments(tmp_path):
    repo = _repo(tmp_path)
    repo.add(ProcessedMail(message_id="<b>", body="full body text", has_attachments=True))
    got = repo.get("<b>")
    assert got.body == "full body text"
    assert got.has_attachments is True


def test_set_action_updates(tmp_path):
    repo = _repo(tmp_path)
    repo.add(ProcessedMail(message_id="<a>", action="pending"))
    repo.set_action("<a>", "created", ticket_key="PROD-3")
    got = repo.get("<a>")
    assert got.action == "created" and got.ticket_key == "PROD-3"


def test_list_by_action_since(tmp_path):
    repo = _repo(tmp_path)
    repo.conn.execute(
        "INSERT INTO processed_mails (message_id, action, created_at) VALUES "
        "('<old>','created','2026-06-01 00:00:00'),"
        "('<new>','created','2026-06-29 00:00:00')"
    )
    repo.conn.commit()
    got = repo.list_by_action_since("created", "2026-06-15 00:00:00")
    assert [m.message_id for m in got] == ["<new>"]

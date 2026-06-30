from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.thread_ticket_map import ThreadTicket, ThreadTicketRepo


def _repo(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return ThreadTicketRepo(conn)


def test_get_missing_returns_none(tmp_path):
    assert _repo(tmp_path).get("conv-x") is None


def test_add_then_get(tmp_path):
    repo = _repo(tmp_path)
    repo.add("conv-1", "PROD-7", source_message_id="<mid-1>")

    got = repo.get("conv-1")
    assert isinstance(got, ThreadTicket)
    assert got.ticket_key == "PROD-7"
    assert got.source_message_id == "<mid-1>"
    assert got.link_replied is False
    assert got.statuses_notified == []


def test_add_is_idempotent_per_conversation(tmp_path):
    repo = _repo(tmp_path)
    repo.add("conv-1", "PROD-7")
    repo.add("conv-1", "PROD-9")  # ignored — conversation already mapped
    assert repo.get("conv-1").ticket_key == "PROD-7"


def test_owa_id_and_lookup_by_key_and_status_dedup(tmp_path):
    repo = _repo(tmp_path)
    repo.add("conv-1", "PROD-7", source_message_id="<m>", owa_message_id="owa-1")
    by_key = repo.get_by_ticket_key("PROD-7")
    assert by_key.conversation_id == "conv-1" and by_key.owa_message_id == "owa-1"

    repo.mark_link_replied("conv-1")
    assert repo.get("conv-1").link_replied is True

    repo.add_status_notified("conv-1", "Done")
    repo.add_status_notified("conv-1", "Done")  # idempotent
    assert repo.get("conv-1").statuses_notified == ["Done"]

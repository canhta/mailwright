from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.thread_ticket_map import PENDING_KEY, ThreadTicket, ThreadTicketRepo


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


def test_try_claim_is_atomic_only_one_winner_per_conversation(tmp_path):
    repo = _repo(tmp_path)

    first = repo.try_claim("conv-1")
    second = repo.try_claim("conv-1")

    assert first is True
    assert second is False
    assert repo.get("conv-1").ticket_key == PENDING_KEY


def test_finalize_claim_replaces_pending_key(tmp_path):
    repo = _repo(tmp_path)
    repo.try_claim("conv-1")

    repo.finalize_claim("conv-1", "PROD-7", source_message_id="<mid-1>", owa_message_id="owa-1")

    got = repo.get("conv-1")
    assert got.ticket_key == "PROD-7"
    assert got.source_message_id == "<mid-1>"
    assert got.owa_message_id == "owa-1"


def test_release_claim_allows_reclaiming(tmp_path):
    repo = _repo(tmp_path)
    repo.try_claim("conv-1")

    repo.release_claim("conv-1")

    assert repo.get("conv-1") is None
    assert repo.try_claim("conv-1") is True


def test_release_claim_does_not_touch_finalized_row(tmp_path):
    repo = _repo(tmp_path)
    repo.try_claim("conv-1")
    repo.finalize_claim("conv-1", "PROD-7")

    repo.release_claim("conv-1")  # must be a no-op once finalized

    assert repo.get("conv-1").ticket_key == "PROD-7"

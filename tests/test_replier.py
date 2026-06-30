from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.pipeline.replier import Replier
from mailwright.repositories.thread_ticket_map import ThreadTicketRepo


class FakeOwa:
    def __init__(self):
        self.replies = []

    def reply_all(self, mid, comment):
        self.replies.append((mid, comment))


def _repo(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return ThreadTicketRepo(conn)


def test_reply_link_sends_once_and_marks(tmp_path):
    repo = _repo(tmp_path)
    repo.add("c", "PROD-7", owa_message_id="owa-1")
    owa = FakeOwa()
    r = Replier(owa, repo)
    assert r.reply_link("c", "owa-1", "PROD-7", "https://x/PROD-7") is True
    assert len(owa.replies) == 1 and "PROD-7" in owa.replies[0][1]
    assert repo.get("c").link_replied is True
    # second call is a no-op (already replied)
    assert r.reply_link("c", "owa-1", "PROD-7", "https://x/PROD-7") is False
    assert len(owa.replies) == 1


def test_reply_link_skips_without_owa_id(tmp_path):
    repo = _repo(tmp_path)
    repo.add("c", "PROD-7")
    owa = FakeOwa()
    assert Replier(owa, repo).reply_link("c", None, "PROD-7", "u") is False
    assert owa.replies == []

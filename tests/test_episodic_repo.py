from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.episodic import EpisodicRepo


def _repo(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return EpisodicRepo(conn)


def test_add_and_fts_search(tmp_path):
    repo = _repo(tmp_path)
    repo.add("ticket_created", "Created PROD-7 for CSV export request", ref="PROD-7")
    repo.add("ignored", "Newsletter about office party")

    hits = repo.search("CSV export")
    assert len(hits) == 1 and hits[0].ref == "PROD-7"
    assert repo.search("party")[0].type == "ignored"


def test_recent_orders_newest_first(tmp_path):
    repo = _repo(tmp_path)
    a = repo.add("x", "first")
    b = repo.add("x", "second")
    recent = repo.recent(limit=2)
    assert [e.id for e in recent] == [b, a]

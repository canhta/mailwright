from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.rulebook import RulebookRepo


def _repo(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return RulebookRepo(conn)


def test_active_render_and_proposed_activation(tmp_path):
    repo = _repo(tmp_path)
    repo.add("hard", "Never auto-reply outside the company domain.")
    pid = repo.add("soft", "Prefer terse summaries.", status="proposed")
    assert "Never auto-reply" in repo.render()
    assert "Prefer terse" not in repo.render()  # proposed not rendered
    assert [r.id for r in repo.list_proposed()] == [pid]
    repo.activate(pid)
    assert "Prefer terse" in repo.render()

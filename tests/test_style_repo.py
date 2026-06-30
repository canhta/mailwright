from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.style import StyleRepo


def test_style_get_set(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    repo = StyleRepo(conn)
    assert repo.get() == ""
    repo.set("Short greetings, bullet points, no hedging.")
    assert "bullet points" in repo.get()

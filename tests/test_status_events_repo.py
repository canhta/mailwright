from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.status_events import StatusEvent, StatusEventRepo


def test_add_and_list_since(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    repo = StatusEventRepo(conn)
    conn.execute(
        "INSERT INTO status_events (ticket_key, status, created_at) VALUES (?,?,?)",
        ("PROD-1", "Done", "2026-06-01 00:00:00"),
    )
    conn.commit()
    repo.add("PROD-2", "In Prod")  # created_at = now (recent)
    recent = repo.list_since("2026-06-15 00:00:00")
    keys = [e.ticket_key for e in recent]
    assert "PROD-2" in keys and "PROD-1" not in keys
    assert all(isinstance(e, StatusEvent) for e in recent)

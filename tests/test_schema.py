import sqlite3

from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db


def test_init_db_creates_processed_mails(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = get_connection(db_path)
    init_db(conn)

    cols = {row["name"] for row in conn.execute("PRAGMA table_info(processed_mails)")}
    assert {
        "message_id",
        "conversation_id",
        "sender",
        "subject",
        "received_at",
        "classification",
        "action",
        "ticket_key",
    } <= cols


def test_init_db_is_idempotent(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    init_db(conn)  # must not raise
    assert isinstance(conn, sqlite3.Connection)

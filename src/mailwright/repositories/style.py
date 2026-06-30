import sqlite3

_KEY = "style_profile"


class StyleRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self) -> str:
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (_KEY,)).fetchone()
        return str(row["value"]) if row else ""

    def set(self, text: str) -> None:
        self.conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_KEY, text),
        )
        self.conn.commit()

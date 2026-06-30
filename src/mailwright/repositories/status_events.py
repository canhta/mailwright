import sqlite3
from dataclasses import dataclass


@dataclass
class StatusEvent:
    ticket_key: str
    status: str
    created_at: str


class StatusEventRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, ticket_key: str, status: str) -> None:
        self.conn.execute(
            "INSERT INTO status_events (ticket_key, status) VALUES (?, ?)", (ticket_key, status)
        )
        self.conn.commit()

    def list_since(self, since: str) -> list[StatusEvent]:
        rows = self.conn.execute(
            "SELECT ticket_key, status, created_at FROM status_events "
            "WHERE created_at > ? ORDER BY created_at",
            (since,),
        ).fetchall()
        return [StatusEvent(r["ticket_key"], r["status"], r["created_at"]) for r in rows]

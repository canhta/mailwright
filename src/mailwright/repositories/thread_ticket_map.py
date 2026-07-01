import json
import sqlite3
from dataclasses import dataclass, field

PENDING_KEY = "__pending__"


@dataclass
class ThreadTicket:
    conversation_id: str
    ticket_key: str
    source_message_id: str | None = None
    owa_message_id: str | None = None
    link_replied: bool = False
    statuses_notified: list[str] = field(default_factory=list)


class ThreadTicketRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _to_obj(self, row) -> ThreadTicket:
        return ThreadTicket(
            conversation_id=row["conversation_id"],
            ticket_key=row["ticket_key"],
            source_message_id=row["source_message_id"],
            owa_message_id=row["owa_message_id"],
            link_replied=bool(row["link_replied"]),
            statuses_notified=json.loads(row["statuses_notified"]),
        )

    def get(self, conversation_id: str) -> ThreadTicket | None:
        row = self.conn.execute(
            """
            SELECT conversation_id, ticket_key, source_message_id, owa_message_id,
                   link_replied, statuses_notified
            FROM thread_ticket_map WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
        return self._to_obj(row) if row else None

    def get_by_ticket_key(self, ticket_key: str) -> "ThreadTicket | None":
        row = self.conn.execute(
            """
            SELECT conversation_id, ticket_key, source_message_id, owa_message_id,
                   link_replied, statuses_notified
            FROM thread_ticket_map WHERE ticket_key = ?
            """,
            (ticket_key,),
        ).fetchone()
        return self._to_obj(row) if row else None

    def add(
        self,
        conversation_id: str,
        ticket_key: str,
        source_message_id: str | None = None,
        owa_message_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO thread_ticket_map
                (conversation_id, ticket_key, source_message_id, owa_message_id)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, ticket_key, source_message_id, owa_message_id),
        )
        self.conn.commit()

    def try_claim(self, conversation_id: str) -> bool:
        """Atomically stake a claim on a conversation before creating its ticket.

        Two processes racing to handle the same thread both hit this — the
        PRIMARY KEY on conversation_id means SQLite serializes the two
        INSERTs and only one can win. The loser must not create a ticket.
        """
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO thread_ticket_map (conversation_id, ticket_key) VALUES (?, ?)",
            (conversation_id, PENDING_KEY),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def finalize_claim(
        self,
        conversation_id: str,
        ticket_key: str,
        source_message_id: str | None = None,
        owa_message_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE thread_ticket_map
            SET ticket_key = ?, source_message_id = ?, owa_message_id = ?
            WHERE conversation_id = ?
            """,
            (ticket_key, source_message_id, owa_message_id, conversation_id),
        )
        self.conn.commit()

    def release_claim(self, conversation_id: str) -> None:
        self.conn.execute(
            "DELETE FROM thread_ticket_map WHERE conversation_id = ? AND ticket_key = ?",
            (conversation_id, PENDING_KEY),
        )
        self.conn.commit()

    def mark_link_replied(self, conversation_id: str) -> None:
        self.conn.execute(
            "UPDATE thread_ticket_map SET link_replied = 1 WHERE conversation_id = ?",
            (conversation_id,),
        )
        self.conn.commit()

    def add_status_notified(self, conversation_id: str, status: str) -> None:
        rec = self.get(conversation_id)
        if rec is None or status in rec.statuses_notified:
            return
        updated = rec.statuses_notified + [status]
        self.conn.execute(
            "UPDATE thread_ticket_map SET statuses_notified = ? WHERE conversation_id = ?",
            (json.dumps(updated), conversation_id),
        )
        self.conn.commit()

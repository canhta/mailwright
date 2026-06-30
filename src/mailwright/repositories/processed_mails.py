import sqlite3
from dataclasses import dataclass


@dataclass
class ProcessedMail:
    message_id: str
    conversation_id: str | None = None
    sender: str | None = None
    subject: str | None = None
    received_at: str | None = None
    classification: str | None = None
    action: str | None = None
    ticket_key: str | None = None
    body: str | None = None
    has_attachments: bool = False


class ProcessedMailRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def exists(self, message_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM processed_mails WHERE message_id = ?", (message_id,)
        ).fetchone()
        return row is not None

    def add(self, mail: ProcessedMail) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO processed_mails
                (message_id, conversation_id, sender, subject, received_at,
                 classification, action, ticket_key, body, has_attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mail.message_id,
                mail.conversation_id,
                mail.sender,
                mail.subject,
                mail.received_at,
                mail.classification,
                mail.action,
                mail.ticket_key,
                mail.body,
                int(mail.has_attachments),
            ),
        )
        self.conn.commit()

    def get(self, message_id: str) -> ProcessedMail | None:
        row = self.conn.execute(
            """
            SELECT message_id, conversation_id, sender, subject, received_at,
                   classification, action, ticket_key, body, has_attachments
            FROM processed_mails WHERE message_id = ?
            """,
            (message_id,),
        ).fetchone()
        if row is None:
            return None
        d = {k: row[k] for k in row.keys()}  # noqa: SIM118
        d["has_attachments"] = bool(d.get("has_attachments"))
        return ProcessedMail(**d)

    def set_action(self, message_id: str, action: str, ticket_key: str | None = None) -> None:
        self.conn.execute(
            "UPDATE processed_mails SET action = ?, ticket_key = ? WHERE message_id = ?",
            (action, ticket_key, message_id),
        )
        self.conn.commit()

    def _to_obj(self, r) -> ProcessedMail:
        d = {k: r[k] for k in r.keys()}  # noqa: SIM118
        d["has_attachments"] = bool(d.get("has_attachments"))
        return ProcessedMail(**d)

    def list_by_action(self, action: str, limit: int = 20) -> list[ProcessedMail]:
        rows = self.conn.execute(
            "SELECT message_id, conversation_id, sender, subject, received_at, "
            "classification, action, ticket_key, body, has_attachments "
            "FROM processed_mails WHERE action = ? ORDER BY created_at DESC LIMIT ?",
            (action, limit),
        ).fetchall()
        return [self._to_obj(r) for r in rows]

    def list_by_action_since(self, action: str, since: str) -> list[ProcessedMail]:
        rows = self.conn.execute(
            "SELECT message_id, conversation_id, sender, subject, received_at, "
            "classification, action, ticket_key, body, has_attachments "
            "FROM processed_mails WHERE action = ? AND created_at > ? ORDER BY created_at",
            (action, since),
        ).fetchall()
        return [self._to_obj(r) for r in rows]

import json
import sqlite3
from dataclasses import dataclass


@dataclass
class ApprovalRecord:
    id: int
    kind: str
    payload: dict
    status: str
    tg_message_id: int | None = None


class ApprovalRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, kind: str, payload: dict, status: str = "pending") -> int:
        cur = self.conn.execute(
            "INSERT INTO pending_approvals (kind, payload, status) VALUES (?, ?, ?)",
            (kind, json.dumps(payload), status),
        )
        self.conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def _row(self, row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            id=row["id"],
            kind=row["kind"],
            payload=json.loads(row["payload"]),
            status=row["status"],
            tg_message_id=row["tg_message_id"],
        )

    def get(self, approval_id: int) -> ApprovalRecord | None:
        row = self.conn.execute(
            "SELECT id, kind, payload, status, tg_message_id FROM pending_approvals WHERE id = ?",
            (approval_id,),
        ).fetchone()
        return self._row(row) if row else None

    def list_pending(self) -> list[ApprovalRecord]:
        rows = self.conn.execute(
            "SELECT id, kind, payload, status, tg_message_id FROM pending_approvals "
            "WHERE status = 'pending' ORDER BY id"
        ).fetchall()
        return [self._row(r) for r in rows]

    def set_status(self, approval_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE pending_approvals SET status = ? WHERE id = ?", (status, approval_id)
        )
        self.conn.commit()

    def set_tg_message_id(self, approval_id: int, message_id: int) -> None:
        self.conn.execute(
            "UPDATE pending_approvals SET tg_message_id = ? WHERE id = ?", (message_id, approval_id)
        )
        self.conn.commit()

    def update_payload(self, approval_id: int, payload: dict) -> None:
        self.conn.execute(
            "UPDATE pending_approvals SET payload = ? WHERE id = ?",
            (json.dumps(payload), approval_id),
        )
        self.conn.commit()

    def list_pending_older_than(self, cutoff: str) -> list[ApprovalRecord]:
        rows = self.conn.execute(
            "SELECT id, kind, payload, status, tg_message_id FROM pending_approvals "
            "WHERE status = 'pending' AND created_at < ? ORDER BY id",
            (cutoff,),
        ).fetchall()
        return [self._row(r) for r in rows]

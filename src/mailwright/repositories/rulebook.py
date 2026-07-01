import sqlite3
from dataclasses import dataclass


@dataclass
class Rule:
    id: int
    kind: str
    text: str
    status: str


class RulebookRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, kind: str, text: str, status: str = "active") -> int:
        cur = self.conn.execute(
            "INSERT INTO rulebook (kind, text, status) VALUES (?, ?, ?)", (kind, text, status)
        )
        self.conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def list_all(self) -> list[Rule]:
        rows = self.conn.execute(
            "SELECT id, kind, text, status FROM rulebook ORDER BY id"
        ).fetchall()
        return [Rule(r["id"], r["kind"], r["text"], r["status"]) for r in rows]

    def update(self, rule_id: int, text: str | None = None, status: str | None = None) -> bool:
        if text is None and status is None:
            return False
        fields = []
        values: list[object] = []
        if text is not None:
            fields.append("text = ?")
            values.append(text)
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        values.append(rule_id)
        cur = self.conn.execute(f"UPDATE rulebook SET {', '.join(fields)} WHERE id = ?", values)
        self.conn.commit()
        return cur.rowcount > 0

    def _list(self, status: str) -> list[Rule]:
        rows = self.conn.execute(
            "SELECT id, kind, text, status FROM rulebook WHERE status = ? ORDER BY id", (status,)
        ).fetchall()
        return [Rule(r["id"], r["kind"], r["text"], r["status"]) for r in rows]

    def list_active(self) -> list[Rule]:
        return self._list("active")

    def list_proposed(self) -> list[Rule]:
        return self._list("proposed")

    def activate(self, rule_id: int) -> None:
        self.conn.execute("UPDATE rulebook SET status = 'active' WHERE id = ?", (rule_id,))
        self.conn.commit()

    def render(self) -> str:
        rules = self.list_active()
        if not rules:
            return ""
        return "\n".join(f"{i}. {r.text}" for i, r in enumerate(rules, 1))

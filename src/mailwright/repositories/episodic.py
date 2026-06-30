import re
import sqlite3
from dataclasses import dataclass


def _fts_query(query: str) -> str:
    tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", query) if t]
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


@dataclass
class EpisodicEntry:
    id: int
    ts: str
    type: str
    ref: str | None
    content: str


class EpisodicRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, type: str, content: str, ref: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO episodic_log (type, ref, content) VALUES (?, ?, ?)", (type, ref, content)
        )
        assert cur.lastrowid is not None
        rowid = cur.lastrowid
        self.conn.execute(
            "INSERT INTO episodic_fts (rowid, content) VALUES (?, ?)", (rowid, content)
        )
        self.conn.commit()
        return rowid

    def _by_ids(self, ids: list[int]) -> list[EpisodicEntry]:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT id, ts, type, ref, content FROM episodic_log WHERE id IN ({marks})", ids
        ).fetchall()
        order = {rid: i for i, rid in enumerate(ids)}
        out = [EpisodicEntry(r["id"], r["ts"], r["type"], r["ref"], r["content"]) for r in rows]
        out.sort(key=lambda e: order[e.id])
        return out

    def search(self, query: str, limit: int = 10) -> list[EpisodicEntry]:
        rows = self.conn.execute(
            "SELECT rowid FROM episodic_fts WHERE episodic_fts MATCH ? LIMIT ?",
            (_fts_query(query), limit),
        ).fetchall()
        return self._by_ids([r["rowid"] for r in rows])

    def recent(self, limit: int = 10) -> list[EpisodicEntry]:
        rows = self.conn.execute(
            "SELECT id, ts, type, ref, content FROM episodic_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [EpisodicEntry(r["id"], r["ts"], r["type"], r["ref"], r["content"]) for r in rows]

    def delete_by_ref(self, ref: str) -> int:
        ids = [
            r[0]
            for r in self.conn.execute(
                "SELECT id FROM episodic_log WHERE ref = ?", (ref,)
            ).fetchall()
        ]
        if not ids:
            return 0
        for rid in ids:
            self.conn.execute("DELETE FROM episodic_fts WHERE rowid = ?", (rid,))
        self.conn.execute(f"DELETE FROM episodic_log WHERE id IN ({','.join('?' * len(ids))})", ids)
        self.conn.commit()
        return len(ids)

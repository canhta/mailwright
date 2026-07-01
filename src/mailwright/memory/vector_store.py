import sqlite3

import numpy as np


class VectorStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, kind: str, text: str, vector: list[float], ref: str | None = None) -> int:
        blob = np.asarray(vector, dtype=np.float32).tobytes()
        cur = self.conn.execute(
            "INSERT INTO embeddings (kind, text, ref, vector) VALUES (?, ?, ?, ?)",
            (kind, text, ref, blob),
        )
        self.conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def delete_by_ref(self, ref: str) -> int:
        cur = self.conn.execute("DELETE FROM embeddings WHERE ref = ?", (ref,))
        self.conn.commit()
        return cur.rowcount

    def list_by_kind(self, kind: str) -> list[tuple[int, str, str]]:
        rows = self.conn.execute(
            "SELECT id, text, created_at FROM embeddings WHERE kind = ? ORDER BY id", (kind,)
        ).fetchall()
        return [(r["id"], r["text"], r["created_at"]) for r in rows]

    def delete(self, row_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM embeddings WHERE id = ?", (row_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def search(self, kind: str, query_vector: list[float], k: int) -> list[tuple[str, float]]:
        q = np.asarray(query_vector, dtype=np.float32)
        qn = np.linalg.norm(q) or 1.0
        rows = self.conn.execute(
            "SELECT text, vector FROM embeddings WHERE kind = ?", (kind,)
        ).fetchall()
        scored = []
        for row in rows:
            v = np.frombuffer(row["vector"], dtype=np.float32)
            denom = (np.linalg.norm(v) or 1.0) * qn
            scored.append((row["text"], float(np.dot(q, v) / denom)))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]

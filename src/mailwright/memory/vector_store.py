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

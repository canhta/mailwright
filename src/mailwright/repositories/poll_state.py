import json
import sqlite3
from dataclasses import dataclass

_KEY = "poll_state"


@dataclass
class PollState:
    interval_seconds: int
    paused: bool
    last_poll_at: float | None


class PollStateRepo:
    def __init__(self, conn: sqlite3.Connection, default_interval_seconds: int) -> None:
        self.conn = conn
        self._default_interval = default_interval_seconds

    def get(self) -> PollState:
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (_KEY,)).fetchone()
        if not row:
            return PollState(self._default_interval, False, None)
        data = json.loads(row["value"])
        return PollState(data["interval_seconds"], data["paused"], data["last_poll_at"])

    def _save(self, state: PollState) -> None:
        value = json.dumps(
            {
                "interval_seconds": state.interval_seconds,
                "paused": state.paused,
                "last_poll_at": state.last_poll_at,
            }
        )
        self.conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_KEY, value),
        )
        self.conn.commit()

    def set_interval(self, seconds: int) -> None:
        state = self.get()
        state.interval_seconds = seconds
        self._save(state)

    def set_paused(self, paused: bool) -> None:
        state = self.get()
        state.paused = paused
        self._save(state)

    def mark_polled(self, now: float) -> None:
        state = self.get()
        state.last_poll_at = now
        self._save(state)

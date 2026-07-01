import json
import sqlite3
from dataclasses import dataclass

_KEY = "runtime_config"


@dataclass
class RuntimeConfig:
    interval_seconds: int
    paused: bool
    last_poll_at: float | None
    reply_all_enabled: bool
    urgent_ping_enabled: bool
    sender_allowlist: list[str]


class RuntimeConfigRepo:
    def __init__(
        self,
        conn: sqlite3.Connection,
        default_interval_seconds: int,
        default_sender_allowlist: list[str] | None = None,
    ) -> None:
        self.conn = conn
        self._default_interval = default_interval_seconds
        self._default_senders = list(default_sender_allowlist or [])

    def get(self) -> RuntimeConfig:
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (_KEY,)).fetchone()
        if not row:
            return RuntimeConfig(
                self._default_interval, False, None, True, True, list(self._default_senders)
            )
        data = json.loads(row["value"])
        return RuntimeConfig(
            data["interval_seconds"],
            data["paused"],
            data["last_poll_at"],
            data["reply_all_enabled"],
            data["urgent_ping_enabled"],
            data["sender_allowlist"],
        )

    def _save(self, state: RuntimeConfig) -> None:
        value = json.dumps(
            {
                "interval_seconds": state.interval_seconds,
                "paused": state.paused,
                "last_poll_at": state.last_poll_at,
                "reply_all_enabled": state.reply_all_enabled,
                "urgent_ping_enabled": state.urgent_ping_enabled,
                "sender_allowlist": state.sender_allowlist,
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

    def set_reply_all(self, enabled: bool) -> None:
        state = self.get()
        state.reply_all_enabled = enabled
        self._save(state)

    def set_urgent_ping(self, enabled: bool) -> None:
        state = self.get()
        state.urgent_ping_enabled = enabled
        self._save(state)

    def add_sender(self, entry: str) -> None:
        entry = entry.strip().lower()
        state = self.get()
        if entry not in state.sender_allowlist:
            state.sender_allowlist = [*state.sender_allowlist, entry]
            self._save(state)

    def remove_sender(self, entry: str) -> bool:
        entry = entry.strip().lower()
        state = self.get()
        if entry not in state.sender_allowlist:
            return False
        state.sender_allowlist = [e for e in state.sender_allowlist if e != entry]
        self._save(state)
        return True

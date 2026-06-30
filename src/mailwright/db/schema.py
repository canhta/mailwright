import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS processed_mails (
    message_id      TEXT PRIMARY KEY,
    conversation_id TEXT,
    sender          TEXT,
    subject         TEXT,
    received_at     TEXT,
    classification  TEXT,
    action          TEXT,
    ticket_key      TEXT,
    body            TEXT,
    has_attachments INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS thread_ticket_map (
    conversation_id   TEXT PRIMARY KEY,
    ticket_key        TEXT NOT NULL,
    source_message_id TEXT,
    owa_message_id    TEXT,
    link_replied      INTEGER NOT NULL DEFAULT 0,
    statuses_notified TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pending_approvals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL,
    payload       TEXT NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'pending',
    tg_message_id INTEGER,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS status_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_key TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rulebook (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT,
    text       TEXT,
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS episodic_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT DEFAULT (datetime('now')),
    type    TEXT,
    ref     TEXT,
    content TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(content);

CREATE TABLE IF NOT EXISTS embeddings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT,
    text       TEXT,
    ref        TEXT,
    vector     BLOB,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()

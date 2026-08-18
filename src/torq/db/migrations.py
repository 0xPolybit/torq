"""SQLite schema migrations (PLAN §13).

Migrations are an ordered list of ``(version, sql)`` tuples. The
migration runner applies every entry whose version is greater than
the current ``schema_version``. Each migration must be idempotent
at the application level (the runner only re-runs when the version
moves forward) and must not depend on prior schema_version rows.

To add a migration:

1. Append a new ``(N, sql)`` to ``MIGRATIONS``. ``N`` must be greater
   than every existing version.
2. Keep migrations small and additive. Refrain from renaming /
   dropping columns in the same migration that introduces them.
"""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS torrents (
            id TEXT PRIMARY KEY,
            info_hash_v1 TEXT,
            info_hash_v2 TEXT,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source TEXT,
            save_path TEXT NOT NULL,
            state TEXT NOT NULL,
            progress REAL NOT NULL DEFAULT 0.0,
            total_size INTEGER,
            downloaded INTEGER NOT NULL DEFAULT 0,
            uploaded INTEGER NOT NULL DEFAULT 0,
            download_rate INTEGER NOT NULL DEFAULT 0,
            upload_rate INTEGER NOT NULL DEFAULT 0,
            seeds INTEGER NOT NULL DEFAULT 0,
            peers INTEGER NOT NULL DEFAULT 0,
            ratio REAL NOT NULL DEFAULT 0.0,
            eta_seconds INTEGER,
            category TEXT,
            tags TEXT NOT NULL DEFAULT '[]',
            added_at INTEGER NOT NULL,
            completed_at INTEGER,
            queue_position INTEGER,
            error_message TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_torrents_state ON torrents(state);
        CREATE INDEX IF NOT EXISTS idx_torrents_category ON torrents(category);
        CREATE INDEX IF NOT EXISTS idx_torrents_added_at ON torrents(added_at);
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            torrent_id TEXT,
            kind TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_events_torrent ON events(torrent_id);
        CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """,
    ),
]


def apply(conn: sqlite3.Connection, now: int) -> int:
    """Apply every pending migration. Returns the new schema version."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)"
    )
    current_raw = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]
    current = int(current_raw)
    for version, sql in MIGRATIONS:
        if version > current:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            current = version
    return current


def current_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied migration version, or 0 if uninitialised."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    version_raw = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]
    return int(version_raw)

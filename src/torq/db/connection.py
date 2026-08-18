"""SQLite connection helpers (PLAN §13).

The Torq database is a single ``torq.db`` file under the user's
data directory. Connections use WAL mode for concurrent reads and
``Row`` factory for named access. Foreign keys are enforced.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the database and return a configured connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

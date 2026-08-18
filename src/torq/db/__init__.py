"""Public entry point for the database layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from torq.db.connection import connect
from torq.db.migrations import apply, current_version


def init(db_path: Path, now: int) -> int:
    """Open the database and apply pending migrations. Returns the new version."""
    conn = connect(db_path)
    try:
        return apply(conn, now)
    finally:
        conn.close()


def schema_version(db_path: Path) -> int:
    """Return the current schema version of the database (0 if uninitialised)."""
    conn = connect(db_path)
    try:
        return current_version(conn)
    finally:
        conn.close()


__all__ = ["Any", "connect", "init", "schema_version"]

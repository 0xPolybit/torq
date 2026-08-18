"""Unit tests for the SQLite schema and migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from torq.db import init, schema_version
from torq.db.connection import connect
from torq.db.migrations import MIGRATIONS, apply, current_version


def test_init_creates_database_file(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1_700_000_000)
    assert db_path.exists()


def test_init_creates_parent_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dirs" / "torq.db"
    init(db_path, now=1_700_000_000)
    assert db_path.exists()


def test_init_applies_all_migrations(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    version = init(db_path, now=1_700_000_000)
    assert version == len(MIGRATIONS)
    assert schema_version(db_path) == len(MIGRATIONS)


def test_init_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1_700_000_000)
    # Second call must not raise and must not change the version.
    version = init(db_path, now=1_700_000_001)
    assert version == len(MIGRATIONS)


def test_init_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1_700_000_000)
    conn = connect(db_path)
    try:
        names = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert "torrents" in names
    assert "events" in names
    assert "settings" in names
    assert "schema_version" in names


def test_init_creates_expected_indices(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1_700_000_000)
    conn = connect(db_path)
    try:
        index_names = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    finally:
        conn.close()
    # Indices declared by the migrations.
    assert "idx_torrents_state" in index_names
    assert "idx_torrents_category" in index_names
    assert "idx_torrents_added_at" in index_names
    assert "idx_events_torrent" in index_names
    assert "idx_events_timestamp" in index_names
    assert "idx_events_kind" in index_names


def test_apply_records_timestamp(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    conn = connect(db_path)
    try:
        apply(conn, now=1_700_000_000)
        rows = list(conn.execute("SELECT version, applied_at FROM schema_version ORDER BY version"))
    finally:
        conn.close()
    assert [r["version"] for r in rows] == [v for v, _ in MIGRATIONS]
    assert all(r["applied_at"] == 1_700_000_000 for r in rows)


def test_apply_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    conn = connect(db_path)
    try:
        apply(conn, now=1)
        first_tables = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        apply(conn, now=2)
        second_tables = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert first_tables == second_tables


def test_apply_only_runs_pending_migrations(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    conn = connect(db_path)
    try:
        apply(conn, now=1)  # Apply everything.
        before = conn.execute("SELECT COUNT(*) AS n FROM schema_version").fetchone()["n"]
        # Re-apply: no new migrations should run.
        apply(conn, now=2)
        after = conn.execute("SELECT COUNT(*) AS n FROM schema_version").fetchone()["n"]
    finally:
        conn.close()
    assert before == after == len(MIGRATIONS)


def test_current_version_zero_for_fresh_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    conn = connect(db_path)
    try:
        assert current_version(conn) == 0
    finally:
        conn.close()


def test_current_version_after_init(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1)
    conn = connect(db_path)
    try:
        assert current_version(conn) == len(MIGRATIONS)
    finally:
        conn.close()


def test_torrents_table_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1)
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO torrents (id, name, source_type, save_path, state, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("abc", "ubuntu", "url", "/tmp", "downloading", 1_700_000_000),
        )
        row = conn.execute("SELECT * FROM torrents WHERE id = ?", ("abc",)).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["name"] == "ubuntu"
    assert row["state"] == "downloading"
    assert row["progress"] == 0.0  # default


def test_events_table_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1)
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO torrents (id, name, source_type, save_path, state, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("abc", "ubuntu", "url", "/tmp", "downloading", 1),
        )
        conn.execute(
            "INSERT INTO events (torrent_id, kind, timestamp, payload) VALUES (?, ?, ?, ?)",
            ("abc", "TorrentAdded", 1, '{"foo": 1}'),
        )
        row = conn.execute("SELECT * FROM events WHERE torrent_id = ?", ("abc",)).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["kind"] == "TorrentAdded"
    assert row["payload"] == '{"foo": 1}'


def test_settings_table_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1)
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            ("ui.theme", "dark"),
        )
        row = conn.execute("SELECT * FROM settings WHERE key = ?", ("ui.theme",)).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["value"] == "dark"


def test_foreign_keys_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1)
    conn = connect(db_path)
    try:
        mode = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    finally:
        conn.close()
    assert mode == 1


def test_row_factory_returns_named_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1)
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO torrents (id, name, source_type, save_path, state, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("abc", "ubuntu", "url", "/tmp", "downloading", 1),
        )
        row = conn.execute("SELECT name, state FROM torrents WHERE id = ?", ("abc",)).fetchone()
    finally:
        conn.close()
    assert row["name"] == "ubuntu"  # type: ignore[index]
    assert row["state"] == "downloading"  # type: ignore[index]


def test_wal_mode_active(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1)
    conn = connect(db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"


def test_schema_version_uninitialised_is_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    assert schema_version(db_path) == 0


def test_apply_returns_latest_version(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    conn = connect(db_path)
    try:
        result = apply(conn, now=1)
    finally:
        conn.close()
    assert result == len(MIGRATIONS)


def test_newly_added_migration_runs_after_partial_state(tmp_path: Path) -> None:
    """Simulate a database that has only migration 1 applied, then add v2."""
    db_path = tmp_path / "torq.db"
    conn = connect(db_path)
    try:
        # Apply only migration 1 manually.
        version_1_sql = MIGRATIONS[0][1]
        conn.executescript(
            "CREATE TABLE schema_version "
            "(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL);"
        )
        conn.executescript(version_1_sql)
        conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (1, 1)")
        # Now run apply() — only the remaining migrations should be applied.
        result = apply(conn, now=2)
    finally:
        conn.close()
    assert result == len(MIGRATIONS)
    conn = connect(db_path)
    try:
        names = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert "events" in names
    assert "settings" in names


def test_unknown_table_column_via_select_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    init(db_path, now=1)
    conn = connect(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("SELECT nonexistent FROM torrents")
    finally:
        conn.close()


def test_apply_uses_provided_timestamp(tmp_path: Path) -> None:
    db_path = tmp_path / "torq.db"
    conn = connect(db_path)
    try:
        apply(conn, now=42)
        row = conn.execute(
            "SELECT applied_at FROM schema_version WHERE version = ?",
            (len(MIGRATIONS),),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["applied_at"] == 42

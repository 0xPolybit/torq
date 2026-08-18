"""Unit tests for the daemon lifecycle and single-instance lock."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from torq.config import Config
from torq.daemon import Daemon, DaemonPaths, LockHeldError, PidLock
from torq.events.bus import EventBus
from torq.resume import ResumeEntry, ResumeStore
from torq.torrents.fake import FakeEngine


def _paths(tmp_path: Path) -> DaemonPaths:
    return DaemonPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "log",
        db_path=tmp_path / "data" / "torq.db",
        resume_path=tmp_path / "state" / "resume.json",
        lock_path=tmp_path / "state" / "torq.pid",
        token_path=tmp_path / "state" / "http.token",
    )


def _daemon(tmp_path: Path) -> Daemon:
    return Daemon(
        paths=_paths(tmp_path),
        config=Config(),
        engine=FakeEngine(),
        event_bus=EventBus(),
        now=1_700_000_000,
    )


@pytest.mark.asyncio
async def test_start_creates_database(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    ctx = await d.start()
    try:
        assert ctx.paths.db_path.exists()
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_start_initialises_schema(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    ctx = await d.start()
    try:
        names = {
            row["name"]
            for row in ctx.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "torrents" in names
        assert "events" in names
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_stop_closes_database(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    await d.start()
    await d.stop()
    # After stop the context is None.
    assert d.running is False


@pytest.mark.asyncio
async def test_double_start_raises(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    await d.start()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            await d.start()
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_stop_when_not_running_is_noop(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    await d.stop()  # Must not raise.


@pytest.mark.asyncio
async def test_start_acquires_lock(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    ctx = await d.start()
    try:
        assert ctx.lock.held() is True
        assert ctx.lock.path.exists()
        pid = int(ctx.lock.path.read_text().strip())
        assert pid == os.getpid()
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_stop_releases_lock(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    await d.start()
    await d.stop()
    paths = _paths(tmp_path)
    assert not paths.lock_path.exists()


def test_context_raises_when_not_running(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    with pytest.raises(RuntimeError, match="not running"):
        _ = d.context


def test_running_reflects_lifecycle(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    assert d.running is False


@pytest.mark.asyncio
async def test_double_start_blocks_second_daemon(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    d1 = Daemon(
        paths=paths,
        config=Config(),
        engine=FakeEngine(),
        event_bus=EventBus(),
        now=1_700_000_000,
    )
    await d1.start()
    try:
        d2 = Daemon(
            paths=paths,
            config=Config(),
            engine=FakeEngine(),
            event_bus=EventBus(),
            now=1_700_000_001,
        )
        with pytest.raises(LockHeldError):
            await d2.start()
    finally:
        await d1.stop()


@pytest.mark.asyncio
async def test_load_resume_returns_empty_when_absent(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    await d.start()
    try:
        assert d.load_resume() == []
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_save_resume_round_trips(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    await d.start()
    try:
        entries = [
            ResumeEntry(
                id="t-1",
                info_hash_v1="abc",
                info_hash_v2=None,
                source_type="magnet",
                source="magnet:?xt=urn:btih:abc",
                save_path="/d",
                name="alpha",
                added_at=1_700_000_000,
            ),
            ResumeEntry(
                id="t-2",
                info_hash_v1=None,
                info_hash_v2="def",
                source_type="url",
                source="https://example.com/x.torrent",
                save_path="/d",
                name="beta",
                added_at=1_700_000_001,
            ),
        ]
        d.save_resume(entries)
        loaded = d.load_resume()
        assert [e.id for e in loaded] == ["t-1", "t-2"]
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_save_resume_persists_to_disk(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    d = _daemon(tmp_path)
    await d.start()
    try:
        entries = [
            ResumeEntry(
                id="t-1",
                info_hash_v1="abc",
                info_hash_v2=None,
                source_type="magnet",
                source="magnet:?xt=urn:btih:abc",
                save_path="/d",
                name="alpha",
                added_at=1,
            )
        ]
        d.save_resume(entries)
    finally:
        await d.stop()
    # New daemon reads the persisted file.
    store = ResumeStore(paths.resume_path)
    assert [e.id for e in store.load()] == ["t-1"]


@pytest.mark.asyncio
async def test_load_resume_called_before_start_raises(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    with pytest.raises(RuntimeError, match="not running"):
        d.load_resume()


@pytest.mark.asyncio
async def test_save_resume_called_before_start_raises(tmp_path: Path) -> None:
    d = _daemon(tmp_path)
    with pytest.raises(RuntimeError, match="not running"):
        d.save_resume([])


def test_pid_lock_acquire_creates_file(tmp_path: Path) -> None:
    lock = PidLock(tmp_path / "x.pid")
    lock.acquire()
    try:
        assert lock.path.exists()
        assert lock.held() is True
    finally:
        lock.release()


def test_pid_lock_release_deletes_file(tmp_path: Path) -> None:
    lock = PidLock(tmp_path / "x.pid")
    lock.acquire()
    lock.release()
    assert not lock.path.exists()
    assert lock.held() is False


def test_pid_lock_release_when_not_held_is_noop(tmp_path: Path) -> None:
    lock = PidLock(tmp_path / "x.pid")
    lock.release()  # must not raise


def test_pid_lock_acquire_when_already_held_is_idempotent(tmp_path: Path) -> None:
    lock = PidLock(tmp_path / "x.pid")
    lock.acquire()
    try:
        # Re-acquire while held must not raise or rewrite.
        first_pid = lock.path.read_text().strip()
        lock.acquire()
        second_pid = lock.path.read_text().strip()
        assert first_pid == second_pid
    finally:
        lock.release()


def test_pid_lock_double_acquire_blocked(tmp_path: Path) -> None:
    lock_path = tmp_path / "x.pid"
    lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    lock = PidLock(lock_path)
    with pytest.raises(LockHeldError):
        lock.acquire()


def test_stale_lock_is_replaced(tmp_path: Path) -> None:
    lock_path = tmp_path / "x.pid"
    # Use a PID that does not exist on this platform.
    dead_pid = 0x7FFFFFFE
    lock_path.write_text(f"{dead_pid}\n", encoding="utf-8")
    lock = PidLock(lock_path)
    lock.acquire()
    try:
        assert lock.held() is True
        pid = int(lock.path.read_text().strip())
        assert pid == os.getpid()
    finally:
        lock.release()


def test_lock_with_empty_file_is_treated_as_stale(tmp_path: Path) -> None:
    lock_path = tmp_path / "x.pid"
    lock_path.write_text("", encoding="utf-8")
    lock = PidLock(lock_path)
    lock.acquire()
    try:
        assert lock.held() is True
    finally:
        lock.release()


def test_lock_with_garbage_file_is_treated_as_stale(tmp_path: Path) -> None:
    lock_path = tmp_path / "x.pid"
    lock_path.write_text("not-a-pid", encoding="utf-8")
    lock = PidLock(lock_path)
    lock.acquire()
    try:
        assert lock.held() is True
    finally:
        lock.release()


def test_lock_creates_parent_directory(tmp_path: Path) -> None:
    lock = PidLock(tmp_path / "nested" / "dirs" / "x.pid")
    lock.acquire()
    try:
        assert lock.path.exists()
    finally:
        lock.release()


def test_lock_release_only_removes_own_file(tmp_path: Path) -> None:
    """A different process' lock file must not be deleted by release()."""
    lock_path = tmp_path / "x.pid"
    lock_path.write_text("9999999\n", encoding="utf-8")
    lock = PidLock(lock_path)
    # release() on a non-held lock must not delete the file.
    lock.release()
    assert lock_path.exists()


@pytest.mark.asyncio
async def test_daemon_close_calls_engine_close(tmp_path: Path) -> None:
    """If the engine has a sync close(), Daemon.stop must call it."""
    engine = FakeEngine()
    closed = {"called": False}

    def fake_close() -> None:
        closed["called"] = True

    engine.close = fake_close  # type: ignore[attr-defined]
    d = Daemon(
        paths=_paths(tmp_path),
        config=Config(),
        engine=engine,
        event_bus=EventBus(),
        now=1,
    )
    await d.start()
    await d.stop()
    assert closed["called"] is True


@pytest.mark.asyncio
async def test_daemon_persists_resume_via_engine(tmp_path: Path) -> None:
    """Daemon.stop should call engine.export_resume() and write the result."""
    engine = FakeEngine()
    engine.export_resume = lambda: [  # type: ignore[method-assign, return-value]
        ResumeEntry(
            id="engine-1",
            info_hash_v1="zzz",
            info_hash_v2=None,
            source_type="magnet",
            source="magnet:?xt=urn:btih:zzz",
            save_path="/d",
            name="from-engine",
            added_at=1,
        )
    ]
    d = Daemon(
        paths=_paths(tmp_path),
        config=Config(),
        engine=engine,
        event_bus=EventBus(),
        now=1,
    )
    await d.start()
    await d.stop()
    store = ResumeStore(_paths(tmp_path).resume_path)
    assert [e.id for e in store.load()] == ["engine-1"]


@pytest.mark.asyncio
async def test_daemon_stop_handles_engine_export_not_implemented(tmp_path: Path) -> None:
    engine = FakeEngine()

    def not_implemented() -> list[object]:
        raise NotImplementedError

    engine.export_resume = not_implemented  # type: ignore[method-assign]
    d = Daemon(
        paths=_paths(tmp_path),
        config=Config(),
        engine=engine,
        event_bus=EventBus(),
        now=1,
    )
    await d.start()
    # Must not raise; an empty resume file is the result.
    await d.stop()


@pytest.mark.asyncio
async def test_event_bus_attached_to_context(tmp_path: Path) -> None:
    bus = EventBus()
    d = Daemon(
        paths=_paths(tmp_path),
        config=Config(),
        engine=FakeEngine(),
        event_bus=bus,
        now=1,
    )
    await d.start()
    try:
        assert d.context.event_bus is bus
        assert d.context.engine is not None
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_daemon_paths_dataclass_is_frozen(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        paths.db_path = tmp_path / "other.db"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_context_dataclass_is_frozen(tmp_path: Path) -> None:
    from dataclasses import FrozenInstanceError

    d = _daemon(tmp_path)
    ctx = await d.start()
    try:
        with pytest.raises(FrozenInstanceError):
            ctx.db = None  # type: ignore[misc]
    finally:
        await d.stop()


@pytest.mark.skipif(sys.platform != "win32", reason="windows-specific pid probe")
def test_pid_alive_detects_self_on_windows(tmp_path: Path) -> None:
    # Current process is running, so its PID must be considered alive.
    lock = PidLock(tmp_path / "x.pid")
    lock_path = lock.path
    lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    # Acquiring must fail (we're alive).
    with pytest.raises(LockHeldError):
        lock.acquire()

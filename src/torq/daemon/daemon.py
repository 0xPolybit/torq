"""Daemon lifecycle (PLAN §15-§16).

A :class:`Daemon` ties the engine, event bus, database, resume
store, and HTTP API together. The lifecycle is:

- :meth:`Daemon.start` acquires the single-instance lock, opens
  the database, applies migrations, loads the resume store,
  provisions a bearer token, and binds the loopback HTTP server.
- :meth:`Daemon.stop` flushes the resume store, stops the HTTP
  server, closes the database, and releases the lock.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from torq.api.auth import TokenStore
from torq.api.server import APIServer, ServerConfig
from torq.config import Config as TorqConfig
from torq.daemon.locks import LockHeldError, PidLock
from torq.db import init as init_db
from torq.resume import ResumeEntry, ResumeStore

if TYPE_CHECKING:
    from torq.events.bus import EventBus
    from torq.torrents.engine import TorrentEngine


_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DaemonPaths:
    """Resolved filesystem paths for a daemon invocation."""

    config_dir: Path
    data_dir: Path
    state_dir: Path
    log_dir: Path
    db_path: Path
    resume_path: Path
    lock_path: Path
    token_path: Path


@dataclass(frozen=True, kw_only=True)
class DaemonContext:
    """Container for the components a daemon owns at runtime."""

    paths: DaemonPaths
    config: TorqConfig
    engine: TorrentEngine
    event_bus: EventBus
    db: sqlite3.Connection
    resume: ResumeStore
    tokens: TokenStore
    api: APIServer
    lock: PidLock = field(default_factory=lambda: PidLock(Path("/dev/null")))
    started_at: int = 0


class Daemon:
    """Owns the runtime components and the start/stop lifecycle."""

    def __init__(
        self,
        *,
        paths: DaemonPaths,
        config: TorqConfig,
        engine: TorrentEngine,
        event_bus: EventBus,
        now: int = 0,
    ) -> None:
        self._paths = paths
        self._config = config
        self._engine = engine
        self._bus = event_bus
        self._now = now
        self._context: DaemonContext | None = None

    @property
    def context(self) -> DaemonContext:
        if self._context is None:
            msg = "daemon is not running; call start() first"
            raise RuntimeError(msg)
        return self._context

    @property
    def running(self) -> bool:
        return self._context is not None

    async def start(self) -> DaemonContext:
        """Acquire the lock, open the DB, and load the resume store."""
        if self._context is not None:
            msg = "daemon is already running"
            raise RuntimeError(msg)

        lock = PidLock(self._paths.lock_path)
        try:
            lock.acquire()
        except LockHeldError:
            raise

        try:
            version = init_db(self._paths.db_path, now=self._now)
        except Exception:
            lock.release()
            raise

        db = sqlite3.connect(str(self._paths.db_path), isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        del version

        resume = ResumeStore(self._paths.resume_path)
        resume.load()

        tokens = TokenStore(self._paths.token_path)
        if tokens.path.exists():
            tokens.load()
        else:
            tokens.provision(length=self._config.daemon.token_length)

        api = APIServer(
            config=ServerConfig(
                host=self._config.daemon.host,
                port=self._config.daemon.port,
            ),
            engine=self._engine,
            event_bus=self._bus,
            tokens=tokens,
        )
        try:
            await api.start()
        except Exception:
            lock.release()
            with contextlib.suppress(sqlite3.ProgrammingError):
                db.close()
            raise

        self._context = DaemonContext(
            paths=self._paths,
            config=self._config,
            engine=self._engine,
            event_bus=self._bus,
            db=db,
            resume=resume,
            tokens=tokens,
            api=api,
            lock=lock,
            started_at=self._now,
        )
        _LOG.info(
            "torqd listening on %s:%d (pid %d)",
            api.host,
            api.port,
            0,  # placeholder; see _pid_log
        )
        return self._context

    async def stop(self) -> None:
        """Flush resume, stop the API, close the DB, and release the lock."""
        if self._context is None:
            return
        try:
            # Persist any pending state the engine wants kept across restarts.
            try:
                entries = self._engine.export_resume()
            except NotImplementedError:
                entries = []
            if entries:
                self._context.resume.save(entries)
            # Stop the API server first so in-flight requests drain before
            # the engine closes underneath them.
            with contextlib.suppress(Exception):
                await self._context.api.stop()
            # Close the engine (best-effort).
            close = getattr(self._engine, "close", None)
            if callable(close):
                close()
            # Close the DB connection.
            with contextlib.suppress(sqlite3.ProgrammingError):
                self._context.db.close()
        finally:
            self._context.lock.release()
            self._context = None

    def load_resume(self) -> list[ResumeEntry]:
        """Read the persisted resume file (empty list if absent)."""
        return self.context.resume.load()

    def save_resume(self, entries: list[ResumeEntry]) -> None:
        """Persist the supplied entries atomically."""
        self.context.resume.save(entries)

"""Cross-platform single-instance enforcement (PLAN §15).

The daemon writes its PID to a "lock" file under the state
directory. To determine if the process is still alive we probe the
OS:

- POSIX: send signal 0 (``os.kill(pid, 0)``).
- Windows: open the process with limited query rights and check
  the exit code (``STILL_ACTIVE`` = 259).

If the recorded PID is not alive, the lock file is considered
stale and replaced with the current PID. The lock file is never
written before a check, so two concurrent invocations cannot
both succeed.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import sys
from pathlib import Path

# Constants used by the Windows API below.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return bool(ok) and exit_code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # PID exists but we lack permission to signal it.
        return True
    except OSError:
        return False
    return True


class LockHeldError(RuntimeError):
    """Raised when another daemon instance holds the lock."""


class PidLock:
    """Cross-platform single-instance lock backed by a PID file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._held = False

    @property
    def path(self) -> Path:
        return self._path

    def held(self) -> bool:
        return self._held

    def acquire(self) -> None:
        """Take the lock, replacing a stale PID file. Raises ``LockHeldError``."""
        if self._held:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # If the file exists, the recorded PID must be dead for us to proceed.
        if self._path.exists():
            recorded = self._read_pid()
            if recorded is not None and _pid_alive(recorded):
                msg = f"another torq daemon (pid {recorded}) holds {self._path}"
                raise LockHeldError(msg)
            # Stale or unreadable — remove and continue.
            with contextlib.suppress(FileNotFoundError):
                self._path.unlink()
        self._path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        self._held = True

    def release(self) -> None:
        """Drop the lock. Safe to call multiple times."""
        if not self._held:
            return
        try:
            # Only delete the file if it still points to us.
            recorded = self._read_pid()
            if recorded == os.getpid():
                self._path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self._held = False

    def _read_pid(self) -> int | None:
        try:
            text = self._path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        except OSError:
            return None
        if not text:
            return None
        try:
            return int(text.split()[0])
        except ValueError:
            return None

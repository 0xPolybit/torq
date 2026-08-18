"""Bearer-token authentication for the HTTP API (PLAN §16).

A token is generated when the daemon starts. The plaintext token
is written to ``state_dir/http.token`` with permissions limited to
the current user (POSIX ``0600``). The file mode is best-effort:
on Windows we accept the default ACL and rely on directory ACLs.

The :class:`TokenStore` keeps the plaintext token in memory only
once at startup and serves it to handlers for comparison.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, kw_only=True)
class AuthContext:
    """The bearer token used to authenticate API requests."""

    token: str
    token_path: Path


def generate_token(length: int = 32) -> str:
    """Generate a URL-safe random token of ``length`` bytes."""
    return secrets.token_urlsafe(length)


def write_token_file(path: Path, token: str) -> None:
    """Persist the bearer token with owner-only permissions when possible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp path and atomically rename.
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        tmp.write_text(token, encoding="utf-8")
        # Best-effort permission tightening.
        with contextlib.suppress(OSError):
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def load_token_file(path: Path) -> str:
    """Read a bearer token from disk."""
    return path.read_text(encoding="utf-8").strip()


class TokenStore:
    """In-memory token store backed by an on-disk file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._token: str | None = None

    @property
    def path(self) -> Path:
        return self._path

    def provision(self, length: int = 32) -> AuthContext:
        """Create a fresh token, persist it, and return the context."""
        token = generate_token(length)
        write_token_file(self._path, token)
        self._token = token
        return AuthContext(token=token, token_path=self._path)

    def load(self) -> AuthContext:
        """Read an existing token from disk and remember it."""
        token = load_token_file(self._path)
        self._token = token
        return AuthContext(token=token, token_path=self._path)

    def current(self) -> str | None:
        return self._token

    def clear(self) -> None:
        """Forget the in-memory token. The on-disk file is left intact."""
        self._token = None

    def authorize(self, header: str | None) -> bool:
        """Return True if ``header`` carries the current bearer token."""
        token = self._token
        if token is None or header is None:
            return False
        prefix = "Bearer "
        if not header.startswith(prefix):
            return False
        presented = header[len(prefix) :].strip()
        # Constant-time compare.
        return secrets.compare_digest(presented, token)

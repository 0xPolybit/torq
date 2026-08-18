"""Application directory resolution (PLAN §12).

Wraps :mod:`platformdirs` so the rest of the codebase has a single
import surface and so the directory layout can be documented in one
place. Every accessor returns a ``pathlib.Path``; directories are
*not* created automatically — callers that need them should call
``mkdir(parents=True, exist_ok=True)``.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs

APPNAME = "torq"
APPNAME_AUTHOR = "Polybit"


def config_dir() -> Path:
    """User-specific config directory (``$XDG_CONFIG_HOME/torq``)."""
    return Path(platformdirs.user_config_dir(APPNAME, APPNAME_AUTHOR))


def data_dir() -> Path:
    """User-specific data directory (``$XDG_DATA_HOME/torq``)."""
    return Path(platformdirs.user_data_dir(APPNAME, APPNAME_AUTHOR))


def state_dir() -> Path:
    """User-specific state directory (``$XDG_STATE_HOME/torq``)."""
    return Path(platformdirs.user_state_dir(APPNAME, APPNAME_AUTHOR))


def cache_dir() -> Path:
    """User-specific cache directory (``$XDG_CACHE_HOME/torq``)."""
    return Path(platformdirs.user_cache_dir(APPNAME, APPNAME_AUTHOR))


def log_dir() -> Path:
    """User-specific log directory (``$XDG_STATE_HOME/torq/log``)."""
    return Path(platformdirs.user_log_dir(APPNAME, APPNAME_AUTHOR))


def ensure_dirs() -> dict[str, Path]:
    """Create and return every directory Torq needs on first run."""
    dirs = {
        "config": config_dir(),
        "data": data_dir(),
        "state": state_dir(),
        "cache": cache_dir(),
        "log": log_dir(),
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs

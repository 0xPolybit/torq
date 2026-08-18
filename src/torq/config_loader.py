"""TOML config loader (PLAN §12).

Reads a TOML file, validates the contents against the dataclass
schema in :mod:`torq.config`, and returns a :class:`Config` instance.
Missing files return defaults. Unknown sections are silently
ignored, but unknown keys within a known section raise ``ValueError``
so typos surface immediately.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any

try:
    import tomllib  # pyright: ignore[reportMissingImports]  # Python 3.11+
except ImportError:  # pragma: no cover — Python 3.11+ is required
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

from torq.appdirs import config_dir
from torq.config import (
    Config,
    DaemonConfig,
    DownloadsConfig,
    LoggingConfig,
    NetworkConfig,
)


def default_config_path() -> Path:
    """Return the default config path (``config_dir/torq.toml``)."""
    return config_dir() / "torq.toml"


def load_config(path: Path | None = None) -> Config:
    """Load and validate a config file. Returns defaults if absent."""
    if path is None:
        path = default_config_path()
    if not path.exists():
        return Config()
    with path.open("rb") as f:
        data = tomllib.load(f)
    return _parse(data)


def _parse(data: dict[str, Any]) -> Config:
    return Config(
        daemon=_section(DaemonConfig, data.get("daemon", {}), "daemon"),
        downloads=_section(DownloadsConfig, data.get("downloads", {}), "downloads"),
        network=_section(NetworkConfig, data.get("network", {}), "network"),
        logging=_section(LoggingConfig, data.get("logging", {}), "logging"),
    )


def _section(
    cls: type[Any], raw: dict[str, Any], section_name: str
) -> Any:
    """Build a section dataclass, rejecting unknown keys."""
    if not isinstance(raw, dict):
        msg = f"config section [{section_name}] must be a table, got {type(raw).__name__}"
        raise ValueError(msg)
    valid = {f.name for f in fields(cls)}
    unknown = set(raw) - valid
    if unknown:
        joined = ", ".join(sorted(unknown))
        msg = f"unknown keys in [{section_name}]: {joined}"
        raise ValueError(msg)
    # Coerce list-shaped values to tuples so callers always see the
    # declared container type.
    coerced: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in raw:
            continue
        value = raw[f.name]
        ftype = f.type
        if ftype.startswith("tuple[") and isinstance(value, list):
            value = tuple(value)
        coerced[f.name] = value
    return cls(**coerced)


def expand_user(path: str | Path) -> Path:
    """Expand ``~`` and return a ``Path``."""
    return Path(path).expanduser()

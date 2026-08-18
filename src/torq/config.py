"""Torq configuration model (PLAN §12).

The configuration is loaded from a TOML file (default location
``config_dir/torq.toml``) and validated into a tree of frozen
dataclasses. Defaults exist for every field so a missing config file
yields a fully usable ``Config`` instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DaemonConfig:
    """Daemon process configuration."""

    host: str = "127.0.0.1"
    port: int = 8910
    db_path: str = ""  # resolved at runtime by the daemon
    resume_dir: str = ""  # resolved at runtime by the daemon
    token_length: int = 32


@dataclass(frozen=True)
class DownloadsConfig:
    """Defaults applied when the caller does not specify them."""

    default_save_path: str = ""
    start_paused: bool = False


@dataclass(frozen=True)
class NetworkConfig:
    """Network-layer defaults."""

    listen_ports: tuple[int, int] = (6881, 6891)
    download_limit: int = 0  # bytes/sec; 0 == unlimited
    upload_limit: int = 0


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"


@dataclass(frozen=True)
class Config:
    """Top-level configuration."""

    daemon: DaemonConfig = field(default_factory=DaemonConfig)
    downloads: DownloadsConfig = field(default_factory=DownloadsConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

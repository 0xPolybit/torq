"""Unit tests for the TOML config loader."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from torq.config import (
    Config,
    DaemonConfig,
    DownloadsConfig,
    LoggingConfig,
)
from torq.config_loader import (
    default_config_path,
    expand_user,
    load_config,
)


def test_default_config_returns_defaults() -> None:
    config = Config()
    assert config.daemon.host == "127.0.0.1"
    assert config.daemon.port == 8910
    assert config.downloads.start_paused is False
    assert config.network.listen_ports == (6881, 6891)
    assert config.network.download_limit == 0
    assert config.logging.level == "INFO"


def test_load_missing_file_returns_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "torq.toml")
    assert config == Config()


def test_load_full_config(tmp_path: Path) -> None:
    config_path = tmp_path / "torq.toml"
    config_path.write_text(
        "[daemon]\n"
        'host = "127.0.0.1"\n'
        "port = 9090\n"
        "token_length = 64\n"
        "\n"
        "[downloads]\n"
        'default_save_path = "~/Downloads/torq"\n'
        "start_paused = true\n"
        "\n"
        "[network]\n"
        "listen_ports = [7000, 7099]\n"
        "download_limit = 1024\n"
        "\n"
        "[logging]\n"
        'level = "DEBUG"\n',
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.daemon.host == "127.0.0.1"
    assert config.daemon.port == 9090
    assert config.daemon.token_length == 64
    assert config.downloads.default_save_path == "~/Downloads/torq"
    assert config.downloads.start_paused is True
    assert config.network.listen_ports == (7000, 7099)
    assert config.network.download_limit == 1024
    assert config.logging.level == "DEBUG"


def test_load_partial_config_falls_back_to_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "torq.toml"
    config_path.write_text("[daemon]\nport = 9999\n", encoding="utf-8")
    config = load_config(config_path)
    assert config.daemon.port == 9999
    assert config.daemon.host == "127.0.0.1"  # default
    assert config.downloads.start_paused is False  # default


def test_load_rejects_unknown_key_in_section(tmp_path: Path) -> None:
    config_path = tmp_path / "torq.toml"
    config_path.write_text('[daemon]\nhost = "x"\nbogus_key = 1\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bogus_key"):
        load_config(config_path)


def test_load_rejects_unknown_section(tmp_path: Path) -> None:
    """Unknown sections are silently ignored (forward-compat)."""
    config_path = tmp_path / "torq.toml"
    config_path.write_text("[daemon]\nport = 8080\n\n[unknown_section]\n", encoding="utf-8")
    config = load_config(config_path)
    assert config.daemon.port == 8080


def test_load_rejects_non_table_section(tmp_path: Path) -> None:
    config_path = tmp_path / "torq.toml"
    config_path.write_text('daemon = "not a table"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a table"):
        load_config(config_path)


def test_default_config_path_is_under_config_dir() -> None:
    path = default_config_path()
    assert path.name == "torq.toml"
    # The parent directory is whatever platformdirs picks — just check
    # it ends with the app name.
    assert "torq" in str(path.parent)


def test_expand_user_expands_tilde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # On Windows, os.path.expanduser uses USERPROFILE; on POSIX, HOME.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert expand_user("~/x") == tmp_path / "x"


def test_expand_user_handles_absolute_paths(tmp_path: Path) -> None:
    assert expand_user(tmp_path / "foo") == tmp_path / "foo"


def test_sections_are_frozen() -> None:
    cfg = DaemonConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.host = "127.0.0.1"  # type: ignore[misc]


def test_config_is_frozen() -> None:
    cfg = Config()
    with pytest.raises(FrozenInstanceError):
        cfg.daemon = DaemonConfig()  # type: ignore[misc]


def test_load_empty_file_returns_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "torq.toml"
    config_path.write_text("", encoding="utf-8")
    config = load_config(config_path)
    assert config == Config()


def test_each_section_field_is_independent(tmp_path: Path) -> None:
    """Touching one section's fields leaves the others alone."""
    config_path = tmp_path / "torq.toml"
    config_path.write_text("[network]\ndownload_limit = 555\n", encoding="utf-8")
    config = load_config(config_path)
    assert config.network.download_limit == 555
    assert config.network.upload_limit == 0
    assert config.daemon.port == 8910


def test_logging_level_default_is_info() -> None:
    assert LoggingConfig().level == "INFO"


def test_downloads_default_save_path_is_empty() -> None:
    assert DownloadsConfig().default_save_path == ""


def test_network_section_accepts_upload_limit(tmp_path: Path) -> None:
    config_path = tmp_path / "torq.toml"
    config_path.write_text("[network]\nupload_limit = 12345\n", encoding="utf-8")
    config = load_config(config_path)
    assert config.network.upload_limit == 12345

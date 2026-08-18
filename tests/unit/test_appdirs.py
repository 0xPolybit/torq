"""Unit tests for app-directory resolution."""

from __future__ import annotations

from pathlib import Path

import platformdirs

from torq import appdirs


def test_config_dir_uses_platformdirs() -> None:
    expected = Path(platformdirs.user_config_dir(appdirs.APPNAME, appdirs.APPNAME_AUTHOR))
    assert appdirs.config_dir() == expected


def test_data_dir_uses_platformdirs() -> None:
    expected = Path(platformdirs.user_data_dir(appdirs.APPNAME, appdirs.APPNAME_AUTHOR))
    assert appdirs.data_dir() == expected


def test_state_dir_uses_platformdirs() -> None:
    expected = Path(platformdirs.user_state_dir(appdirs.APPNAME, appdirs.APPNAME_AUTHOR))
    assert appdirs.state_dir() == expected


def test_cache_dir_uses_platformdirs() -> None:
    expected = Path(platformdirs.user_cache_dir(appdirs.APPNAME, appdirs.APPNAME_AUTHOR))
    assert appdirs.cache_dir() == expected


def test_log_dir_uses_platformdirs() -> None:
    expected = Path(platformdirs.user_log_dir(appdirs.APPNAME, appdirs.APPNAME_AUTHOR))
    assert appdirs.log_dir() == expected


def test_ensure_dirs_creates_all(tmp_path: Path) -> None:
    """ensure_dirs creates the directories inside a writable location."""
    # Stub the platformdirs call so we don't pollute the user's home.
    import torq.appdirs as a

    sentinel = tmp_path / "torq"
    original = a.platformdirs.user_config_dir
    a.platformdirs.user_config_dir = lambda *_args, **_kw: str(sentinel / "config")  # type: ignore[assignment]
    try:
        dirs = a.ensure_dirs()
        for path in dirs.values():
            assert path.exists()
            assert path.is_dir()
    finally:
        a.platformdirs.user_config_dir = original  # type: ignore[assignment]


def test_dirs_under_appname() -> None:
    """All appdirs contain the app name."""
    assert appdirs.APPNAME in str(appdirs.config_dir())
    assert appdirs.APPNAME in str(appdirs.data_dir())

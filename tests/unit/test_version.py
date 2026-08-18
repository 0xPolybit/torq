"""Smoke tests for the bootstrap package."""

from __future__ import annotations

from torq import __version__
from torq.version import __version__ as version_module_version


def test_version_is_string() -> None:
    assert isinstance(__version__, str)


def test_version_is_nonempty() -> None:
    assert __version__


def test_version_constants_match() -> None:
    """The package and module must agree to avoid drift."""
    assert __version__ == version_module_version
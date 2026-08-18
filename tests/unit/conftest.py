"""Pytest configuration for unit tests.

Async tests use ``@pytest.mark.asyncio`` (or rely on the auto-mode set in
``pyproject.toml``). This conftest exists so unit tests can be located
anywhere under ``tests/unit/`` without extra boilerplate.
"""

from __future__ import annotations

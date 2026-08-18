"""Unit tests for file-priority constants."""

from __future__ import annotations

import pytest

from torq.torrents.priorities import (
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    MIN_PRIORITY,
    FilePriority,
)


def test_priority_values_match_libtorrent_convention() -> None:
    assert FilePriority.DO_NOT_DOWNLOAD == 0
    assert FilePriority.LOW == 1
    assert FilePriority.NORMAL == 4
    assert FilePriority.HIGH == 7


def test_priorities_are_int_compatible() -> None:
    assert int(FilePriority.NORMAL) == 4
    assert FilePriority.HIGH > FilePriority.LOW


def test_default_priority_is_normal() -> None:
    assert DEFAULT_PRIORITY == FilePriority.NORMAL
    assert DEFAULT_PRIORITY == 4


def test_min_and_max_priorities() -> None:
    assert MIN_PRIORITY == FilePriority.DO_NOT_DOWNLOAD
    assert MAX_PRIORITY == FilePriority.HIGH


@pytest.mark.parametrize("priority", list(FilePriority))
def test_all_priorities_are_non_negative(priority: FilePriority) -> None:
    assert int(priority) >= 0
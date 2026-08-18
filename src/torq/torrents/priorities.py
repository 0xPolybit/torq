"""File priority constants (PLAN §24).

    The numerical values match libtorrent's ``file_priority_t`` so the
    adapter can pass them straight through. Users should normally interact
    with the named enum members, not raw ints.
"""

from __future__ import annotations

from enum import IntEnum


class FilePriority(IntEnum):
    """Named file priorities.

    The numeric values mirror libtorrent's convention where 0 means
    "do not download" and higher numbers mean higher priority.
    """

    DO_NOT_DOWNLOAD = 0
    LOW = 1
    NORMAL = 4
    HIGH = 7


DEFAULT_PRIORITY = FilePriority.NORMAL
MIN_PRIORITY = FilePriority.DO_NOT_DOWNLOAD
MAX_PRIORITY = FilePriority.HIGH

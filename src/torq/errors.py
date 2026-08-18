"""Application-wide error hierarchy (PLAN §27).

The CLI maps these to stable messages and exit codes; the daemon maps them
to HTTP responses. They must never expose Python tracebacks to end users
unless ``--debug`` is set.
"""

from __future__ import annotations


class TorqError(Exception):
    """Root of every error Torq raises intentionally."""


class ConfigurationError(TorqError):
    """Configuration could not be loaded or is invalid."""


class DaemonUnavailableError(TorqError):
    """Local daemon is not running and could not be started."""


class AuthenticationError(TorqError):
    """Local API authentication failed."""


class StorageError(TorqError):
    """SQLite / on-disk state error."""


class TorrentError(TorqError):
    """Torrent-related error."""


class InvalidMagnetError(TorrentError):
    """A magnet URI could not be parsed or is missing required fields.

    The ``uri`` attribute is set when available so callers can show the
    offending value without parsing the message string.
    """

    def __init__(self, reason: str, *, uri: str | None = None) -> None:
        self.uri = uri
        super().__init__(f"invalid magnet ({reason})")


class InvalidTorrentFileError(TorrentError):
    """A ``.torrent`` file is malformed, oversized, or unsafe."""


class DuplicateTorrentError(TorrentError):
    """A torrent with the same info hash is already registered."""


class TorrentNotFoundError(TorrentError):
    """No torrent matches the requested identifier."""


class SearchError(TorqError):
    """Search subsystem error."""


class ProviderUnavailableError(SearchError):
    """A search provider could not be reached."""


class ProviderParseError(SearchError):
    """A search provider returned an unparseable response."""


class ProviderTimeoutError(SearchError):
    """A search provider timed out."""
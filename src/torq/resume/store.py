"""Atomic resume store (PLAN §14).

Persists the metadata required to re-add every torrent on the
next daemon start. The store is a single JSON file written via
write-temp + fsync + rename so a crash mid-write cannot corrupt
the file.

Schema (``torq.resume.json``)::

    [
      {
        "id": "...",
        "info_hash_v1": "...",
        "info_hash_v2": "...",
        "source_type": "magnet" | "url" | "torrent_file",
        "source": "<raw source>",
        "save_path": "/absolute/path",
        "name": "display name",
        "added_at": 1700000000,
        "resume_data": "<base64-encoded bencode>" | null,
        "category": "..." | null,
        "tags": ["..."]
      },
      ...
    ]
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, kw_only=True)
class ResumeEntry:
    """One persisted torrent record."""

    id: str
    info_hash_v1: str | None
    info_hash_v2: str | None
    source_type: str
    source: str | None
    save_path: str
    name: str
    added_at: int
    category: str | None = None
    tags: tuple[str, ...] = ()
    resume_data: bytes | None = None


def atomic_write(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically (write-temp + fsync + rename).

    On POSIX, ``os.replace`` is atomic. On Windows it overwrites
    atomically when both paths are on the same volume.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _encode_entry(entry: ResumeEntry) -> dict[str, Any]:
    d = asdict(entry)
    # JSON cannot encode bytes directly. Encode resume_data as base64.
    if d.get("resume_data") is not None:
        d["resume_data"] = base64.b64encode(d["resume_data"]).decode("ascii")
    # tags is a tuple — JSON serialises it as a list, which is fine.
    return d


def _decode_entry(raw: dict[str, Any]) -> ResumeEntry:
    decoded = dict(raw)
    resume = decoded.get("resume_data")
    if resume is not None and not isinstance(resume, str):
        msg = f"resume_data must be a base64 string, got {type(resume).__name__}"
        raise ValueError(msg)
    if isinstance(resume, str):
        decoded["resume_data"] = base64.b64decode(resume)
    tags = decoded.get("tags", ())
    if isinstance(tags, list):
        decoded["tags"] = tuple(tags)
    return ResumeEntry(**decoded)


class ResumeStore:
    """A persistent list of :class:`ResumeEntry` records."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def load(self) -> list[ResumeEntry]:
        """Return every entry on disk. Empty list if the file does not exist."""
        if not self._path.exists():
            return []
        with self._path.open("rb") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            msg = f"resume file must contain a JSON array, got {type(raw).__name__}"
            raise ValueError(msg)
        return [_decode_entry(item) for item in raw]

    def save(self, entries: Sequence[ResumeEntry]) -> None:
        """Persist ``entries`` atomically, overwriting any existing file."""
        encoded = [_encode_entry(e) for e in entries]
        payload = json.dumps(encoded, indent=2, ensure_ascii=False).encode("utf-8")
        atomic_write(self._path, payload)

    def clear(self) -> None:
        """Delete the on-disk store if present."""
        if self._path.exists():
            self._path.unlink()

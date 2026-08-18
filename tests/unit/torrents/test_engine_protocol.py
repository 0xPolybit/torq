"""Verify :class:`FakeEngine` satisfies the :class:`TorrentEngine` protocol."""

from __future__ import annotations

from pathlib import Path

import pytest

from torq.torrents.engine import TorrentEngine
from torq.torrents.fake import FakeEngine
from torq.torrents.models import AddOptions, TransferLimits


def test_fake_satisfies_engine_protocol() -> None:
    """FakeEngine must be assignable to a TorrentEngine-typed variable."""
    engine: TorrentEngine = FakeEngine()  # mypy will fail here if protocol is unsatisfied
    assert engine is not None


async def test_fake_add_pause_resume_remove() -> None:
    engine = FakeEngine()
    await engine.start()
    ref = await engine.add_magnet(
        "magnet:?xt=urn:btih:deadbeef",
        AddOptions(save_path=Path("/tmp")),
    )
    assert ref.id == "deadbeef"
    statuses = await engine.list()
    assert len(statuses) == 1
    assert statuses[0].id == "deadbeef"

    await engine.pause(ref.id)
    assert (await engine.status(ref.id)).state.value == "paused"

    await engine.resume(ref.id)
    assert (await engine.status(ref.id)).state.value == "downloading"

    await engine.remove(ref.id, delete_data=False)
    assert await engine.list() == []


async def test_fake_add_before_start_raises() -> None:
    engine = FakeEngine()
    with pytest.raises(RuntimeError):
        await engine.add_magnet(
            "magnet:?xt=urn:btih:abc",
            AddOptions(save_path=Path("/tmp")),
        )


async def test_fake_set_global_limits() -> None:
    engine = FakeEngine()
    new_limits = TransferLimits(download_bytes_per_second=1024, upload_bytes_per_second=512)
    await engine.set_global_limits(new_limits)
    assert engine.global_limits == new_limits


async def test_fake_unknown_id_raises() -> None:
    engine = FakeEngine()
    await engine.start()
    with pytest.raises(KeyError):
        await engine.status("nonexistent")
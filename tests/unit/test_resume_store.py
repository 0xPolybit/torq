"""Unit tests for the atomic resume store."""

from __future__ import annotations

import base64
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from torq.resume import ResumeEntry, ResumeStore, atomic_write


def _entry(**kwargs: object) -> ResumeEntry:
    base: dict[str, object] = {
        "id": "t-001",
        "info_hash_v1": "aabbcc",
        "info_hash_v2": None,
        "source_type": "magnet",
        "source": "magnet:?xt=urn:btih:aabbcc",
        "save_path": "/downloads",
        "name": "ubuntu",
        "added_at": 1_700_000_000,
        "category": "linux",
        "tags": ("iso", "ubuntu"),
    }
    base.update(kwargs)
    return ResumeEntry(**base)  # type: ignore[arg-type]


def test_load_returns_empty_when_file_missing(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    assert store.load() == []
    assert store.exists() is False


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    entries = [_entry(id="t-1"), _entry(id="t-2", name="debian", tags=("iso",))]
    store.save(entries)
    loaded = store.load()
    assert [e.id for e in loaded] == ["t-1", "t-2"]
    assert loaded[0].name == "ubuntu"
    assert loaded[0].tags == ("iso", "ubuntu")
    assert loaded[1].tags == ("iso",)


def test_save_overwrites_existing_file(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.save([_entry(id="t-1")])
    store.save([_entry(id="t-2"), _entry(id="t-3")])
    loaded = store.load()
    assert [e.id for e in loaded] == ["t-2", "t-3"]


def test_save_writes_valid_json(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.save([_entry(id="t-1")])
    raw = json.loads(store.path.read_text("utf-8"))
    assert raw[0]["id"] == "t-1"
    assert raw[0]["name"] == "ubuntu"


def test_resume_data_is_base64_encoded_in_file(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    blob = b"\x01\x02\x03\xff\xfe\xfd"
    store.save([_entry(resume_data=blob)])
    raw = json.loads(store.path.read_text("utf-8"))
    assert raw[0]["resume_data"] == base64.b64encode(blob).decode("ascii")


def test_resume_data_round_trips(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    blob = b"bencoded-resume-payload"
    store.save([_entry(resume_data=blob)])
    loaded = store.load()
    assert loaded[0].resume_data == blob


def test_resume_data_none_round_trips(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.save([_entry(resume_data=None)])
    loaded = store.load()
    assert loaded[0].resume_data is None


def test_clear_deletes_file(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.save([_entry()])
    assert store.exists() is True
    store.clear()
    assert store.exists() is False


def test_clear_on_missing_file_is_noop(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.clear()  # must not raise


def test_atomic_write_creates_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dirs" / "out.bin"
    atomic_write(target, b"hello")
    assert target.read_bytes() == b"hello"


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    atomic_write(target, b"first")
    atomic_write(target, b"second")
    assert target.read_bytes() == b"second"


def test_atomic_write_leaves_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    atomic_write(target, b"hello")
    files = list(tmp_path.iterdir())
    assert files == [target]


def test_atomic_write_cleans_up_temp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.bin"
    # Force the rename to fail so the temp file lingers. The cleanup branch
    # in the `finally` block must remove it.
    target.write_bytes(b"original")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr("os.replace", _boom)
    with pytest.raises(OSError, match="simulated crash"):
        atomic_write(target, b"new content")
    tmp = target.with_name(f"{target.name}.tmp")
    assert not tmp.exists()
    # The original file is untouched.
    assert target.read_bytes() == b"original"


def test_atomic_write_replaces_symlink_atomically(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"original")
    link = tmp_path / "link.bin"
    link.symlink_to(target)
    atomic_write(link, b"new")
    assert link.read_bytes() == b"new"


def test_load_rejects_non_array_root(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.path.write_text('{"not":"an array"}', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON array"):
        store.load()


def test_load_rejects_bad_resume_data_type(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.path.write_text(json.dumps([{"id": "x", "resume_data": 123}]), encoding="utf-8")
    with pytest.raises(ValueError, match="base64"):
        store.load()


def test_save_empty_list(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.save([])
    assert store.load() == []


def test_entry_is_frozen() -> None:
    e = _entry()
    with pytest.raises(FrozenInstanceError):
        e.name = "different"  # type: ignore[misc]


def test_unicode_in_name_round_trips(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.save([_entry(name="猫的纪录片")])
    assert store.load()[0].name == "猫的纪录片"


def test_atomic_write_large_payload(tmp_path: Path) -> None:
    target = tmp_path / "big.bin"
    payload = bytes(range(256)) * 1024  # 256 KB
    atomic_write(target, payload)
    assert target.read_bytes() == payload


def test_save_with_many_entries(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    entries = [_entry(id=f"t-{i:04d}", name=f"name-{i}") for i in range(50)]
    store.save(entries)
    loaded = store.load()
    assert len(loaded) == 50
    assert [e.id for e in loaded] == [f"t-{i:04d}" for i in range(50)]


def test_tags_default_is_empty_tuple(tmp_path: Path) -> None:
    e = ResumeEntry(
        id="x",
        info_hash_v1=None,
        info_hash_v2=None,
        source_type="url",
        source="https://example.com/x.torrent",
        save_path="/d",
        name="x",
        added_at=0,
    )
    assert e.tags == ()
    assert e.category is None
    assert e.resume_data is None


def test_save_then_load_preserves_order(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    items = [
        _entry(id=f"t-{i}", added_at=1_700_000_000 + i)
        for i in range(10)
    ]
    # Sequence is the abstract type; passing a list at runtime is fine.
    store.save(items)
    loaded = store.load()
    assert [e.id for e in loaded] == [f"t-{i}" for i in range(10)]


def test_partial_overwrite_succeeds(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "resume.json")
    store.save([_entry(id="t-1")])
    store.save([_entry(id="t-1"), _entry(id="t-2")])
    loaded = store.load()
    assert len(loaded) == 2

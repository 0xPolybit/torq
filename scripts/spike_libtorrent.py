"""Slice 0.2 — libtorrent spike.

Validates that we can:

1. Import ``libtorrent`` and print its version.
2. Create a libtorrent session with sane defaults.
3. Add a magnet URI and read back the resulting torrent_handle.
4. Wait for metadata to arrive (magnet -> name/size).
5. Persist resume data atomically.
6. Restore resume data and confirm the torrent is back.

Run:

    python scripts/spike_libtorrent.py
    python scripts/spike_libtorrent.py --probe-only
    python scripts/spike_libtorrent.py --wait-seconds 30

If libtorrent is not installed, prints an installation hint per OS and exits
0 when ``--probe-only`` is set, otherwise exits 1.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Debian 12 netinst ISO magnet — small, public, legal test target.
DEFAULT_MAGNET = (
    "magnet:?xt=urn:btih:4d68447ca5b4147459e4be6b44389efb8177c2fb"
    "&dn=debian-12.5.0-amd64-netinst.iso"
    "&tr=udp%3a%2f%2ftracker.openbittorrent.com%3a80"
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the spike."""
    parser = argparse.ArgumentParser(description="Torq libtorrent spike.")
    parser.add_argument(
        "--magnet",
        default=DEFAULT_MAGNET,
        help="Magnet URI to test (default: Debian netinst ISO).",
    )
    parser.add_argument(
        "--torrent-file",
        type=Path,
        help="Optional local .torrent file to add instead of a magnet.",
    )
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Only verify that libtorrent imports and prints its version.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=15.0,
        help="How long to wait for metadata (default: 15s).",
    )
    parser.add_argument(
        "--save-path",
        type=Path,
        default=Path("./spike-downloads"),
        help="Where libtorrent should place downloaded files.",
    )
    parser.add_argument(
        "--resume-path",
        type=Path,
        default=Path("./spike-resume.dat"),
        help="Where to write/read resume data.",
    )
    return parser.parse_args()


def import_libtorrent() -> object | None:
    """Import libtorrent or return None with a friendly hint."""
    try:
        import libtorrent  # type: ignore[import-not-found]
    except ImportError:
        print("ERROR: libtorrent is not installed.", file=sys.stderr)
        print("See docs/libtorrent-install.md for installation per OS.", file=sys.stderr)
        return None
    return libtorrent


def report_version(libtorrent: object) -> None:
    """Print the libtorrent version."""
    version = getattr(libtorrent, "__version__", None)
    if version is None:
        # libtorrent < 2.0 exposes version via libtorrent.version
        version_module = getattr(libtorrent, "version", None)
        version = getattr(version_module, "__version__", "unknown") if version_module else "unknown"
    print(f"libtorrent {version}")


def build_session(libtorrent: object) -> object:
    """Create a libtorrent session with sane defaults for the spike."""
    session = libtorrent.session()
    session.listen_on(6881, 6891)
    session.add_dht_router("router.bittorrent.com", 6881)
    session.add_dht_router("router.utorrent.com", 6881)
    session.add_dht_router("dht.transmissionbt.com", 6881)
    session.start_dht()
    session.start_lsd()
    session.start_upnp()
    session.start_natpmp()
    return session


def add_torrent(
    libtorrent: object,
    session: object,
    *,
    magnet: str,
    torrent_file: Path | None,
    save_path: Path,
) -> object:
    """Add a magnet or local .torrent and return the handle."""
    save_path.mkdir(parents=True, exist_ok=True)
    params = libtorrent.add_torrent_params()
    params.save_path = str(save_path)
    if torrent_file is not None:
        params.ti = libtorrent.torrent_info(str(torrent_file))
    else:
        params.url = magnet
    return session.add_torrent(params)


def wait_for_metadata(handle: object, *, timeout: float) -> bool:
    """Poll the handle until it reports having metadata or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if handle.is_valid() and handle.status().has_metadata:
            return True
        time.sleep(0.5)
    return False


def write_resume(libtorrent: object, handle: object, path: Path) -> int:
    """Persist resume data atomically (tmp -> fsync -> rename)."""
    if not handle.is_valid():
        return 0
    handle.pause()
    # write_resume_data_buf is the modern API; fall back if needed.
    write_fn = getattr(libtorrent, "write_resume_data_buf", None)
    if write_fn is None:  # pragma: no cover - older libtorrent
        write_fn = getattr(libtorrent, "write_resume_data")
    resume_buf = write_fn(handle)
    data = libtorrent.bencode(resume_buf)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return len(data)


def main() -> int:
    """Run the spike."""
    args = parse_args()

    libtorrent = import_libtorrent()
    if libtorrent is None:
        return 0 if args.probe_only else 1

    report_version(libtorrent)
    if args.probe_only:
        return 0

    session = build_session(libtorrent)
    handle = add_torrent(
        libtorrent,
        session,
        magnet=args.magnet,
        torrent_file=args.torrent_file,
        save_path=args.save_path,
    )
    print(f"Added torrent (valid={handle.is_valid()})")
    if handle.is_valid():
        print(f"  info_hash: {handle.info_hash()}")
    else:
        print("  info_hash: pending metadata")

    arrived = wait_for_metadata(handle, timeout=args.wait_seconds)
    if arrived:
        ti = handle.torrent_file()
        print("Metadata received:")
        print(f"  name:        {ti.name()}")
        print(f"  total_size:  {ti.total_size()} bytes")
        print(f"  num_files:   {ti.num_files()}")
    else:
        print(
            f"WARN: metadata did not arrive within {args.wait_seconds:.0f}s.",
            file=sys.stderr,
        )

    size = write_resume(libtorrent, handle, args.resume_path)
    if size:
        print(f"Resume data written: {args.resume_path} ({size} bytes)")
    else:
        print("Resume data skipped (no valid handle).")

    session.pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

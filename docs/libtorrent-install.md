# libtorrent Python bindings — installation notes

This document tracks how to install the libtorrent Python bindings on each
target platform. The bindings do **not** ship universal Python wheels, so
installation requires either a system package, a community-built wheel, or
building from source.

## Status as of slice 0.2

| Python | Linux (apt) | macOS (brew) | Windows |
|--------|-------------|--------------|---------|
| 3.12   | yes         | yes          | community wheel |
| 3.13   | yes         | yes          | community wheel |

Python 3.14+ is currently **unsupported** on Windows because no 3.14 wheels
have been published yet. Torq's `.python-version` pins **3.12**, so this gap
does not affect production installs.

## Linux — Debian / Ubuntu (apt)

```bash
sudo apt-get update
sudo apt-get install -y python3-libtorrent
```

The package name follows the pattern `python3.<minor>-libtorrent` if a
specific minor is required:

```bash
sudo apt-get install -y python3.12-libtorrent
```

## Linux — Fedora / RHEL (dnf)

```bash
sudo dnf install -y python3-libtorrent
```

## macOS — Homebrew

```bash
brew install libtorrent-rasterbar
```

The Python bindings are exposed under the Homebrew prefix. Activate the
project venv with the matching Python before running the spike.

## Windows — community wheels

The `libtorrent-rasterbar-wheels` project on PyPI publishes pre-built
wheels for selected Python versions:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install libtorrent-rasterbar-wheels
```

If no wheel exists for the desired Python version, see **Building from
source** below.

## Building from source (any OS)

Required:

- A C++17 compiler (`g++`, `clang++`, or MSVC)
- Boost (≥ 1.74) with development headers
- OpenSSL development headers
- CMake or autotools

Steps (abridged):

```bash
git clone https://github.com/arvidn/libtorrent.git
cd libtorrent
git checkout v2.0.x  # or the latest stable tag
./configure --enable-python-binding --with-libiconv=no
make -j"$(nproc)"
sudo make install
```

Windows builds additionally need vcpkg + Visual Studio Build Tools; this
path is fragile and we recommend the community wheel instead.

## Verifying the spike

```bash
python scripts/spike_libtorrent.py --probe-only
python scripts/spike_libtorrent.py --wait-seconds 30
```

A successful run prints:

```text
libtorrent <version>
Added torrent (valid=True)
  info_hash: <hex>
Metadata received:
  name:        debian-12.5.0-amd64-netinst.iso
  total_size:  <bytes>
  num_files:   1
Resume data written: spike-resume.dat (<bytes>)
```

## Known issues

- The Debian magnet in the spike script sometimes takes >15 s to deliver
  metadata on a clean DHT node. Bump `--wait-seconds` if needed.
- libtorrent 2.0 deprecated `write_resume_data` in favor of
  `write_resume_data_buf`. The spike script prefers the new API and falls
  back automatically.
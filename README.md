# Torq

> Terminal-first BitTorrent client with a polished qBittorrent-like TUI.

Torq is a Python BitTorrent download manager aimed at the terminal. It supports
magnet URIs, `.torrent` files, remote torrent URLs, and a pluggable
multi-provider search system — all fronted by either a scriptable CLI or a
Textual TUI. Downloads run in a background daemon so closing the TUI never
interrupts a transfer.

## Status

**Pre-alpha.** Slice 0.1 — only the package skeleton, tooling, and CI
infrastructure exist. Engine, daemon, CLI, and TUI are not yet implemented.
See [PLAN.md](PLAN.md) for the full roadmap.

## Why Torq

- **Persistent daemon.** Closing the TUI doesn't kill active downloads.
- **Pluggable search.** Provider interface supports Pirate-Bay-compatible
  indexes, generic JSON/RSS providers, and future community plugins — without
  hard-coding any single source.
- **qBittorrent ergonomics in a terminal.** Sortable tables, keyboard-driven
  navigation, multi-screen detail views, and an event-driven UI.
- **Honest scope.** No CAPTCHA bypass, no automatic piracy-mirror rotation,
  no built-in VPN management. The torrent engine does torrent things; the
  search layer is configurable.

## Quick start

Torq is not yet installable from PyPI. Until slice 0.42 (packaging hardening),
the supported way to run it is from source:

```bash
git clone https://github.com/<owner>/torq
cd torq
uv sync --all-extras
uv run torq --version
```

## Documentation

- [PLAN.md](PLAN.md) — architecture, milestones, slice backlog, and CI/CD plan.
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute.
- [SECURITY.md](SECURITY.md) — how to report vulnerabilities.

## License

[MIT](LICENSE).
# Torq — Development Plan

> **Project:** Torq  
> **Type:** Python BitTorrent download manager + CLI/TUI + pluggable torrent-index search  
> **Primary interface:** Terminal  
> **Goal:** Deliver a fast, persistent, scriptable torrent client with a polished qBittorrent-like terminal experience.

---

## 1. Product Definition

Torq is a terminal-first BitTorrent client written primarily in Python. It should be able to:

- Download torrents from magnet URIs.
- Download/open `.torrent` files.
- Accept HTTP(S) URLs that point to `.torrent` metadata files.
- Search configured torrent-index providers from the terminal.
- Provide a dedicated search-provider adapter for The Pirate Bay-compatible indexes, without coupling the application to a single domain or mirror.
- Present search results in an interactive terminal table.
- Start a download directly from a selected search result.
- Keep downloads running after the interactive terminal interface is closed.
- Pause, resume, queue, prioritize, remove, inspect, and monitor torrents.
- Control individual files inside multi-file torrents.
- Show progress, peers, seeds, speed, ETA, ratio, trackers, and torrent metadata.
- Persist state between restarts.
- Support both an interactive full-screen TUI and non-interactive shell commands suitable for scripts.

Torq should feel closer to **qBittorrent in a terminal** than to a simple `wget`-style torrent downloader.

### Example experience

```text
$ torq search "linux iso"

Provider: all

 #  Name                         Size      Seeds  Peers  Provider
 1  Example Linux ISO 2026      4.8 GB    1582   71     provider-a
 2  Example Linux ISO Minimal   1.9 GB     806   39     provider-b

$ torq download 1
Added: Example Linux ISO 2026
ID: 4F2A91C8

$ torq list
 ID        Name                    Progress   Down       Up       ETA
 4F2A91C8  Example Linux ISO      34.7%      21 MB/s    1.2 MB/s  2m 31s
```

Running simply:

```bash
torq
```

should launch the full-screen TUI.

---

## 2. Project Principles

Torq should be designed around the following principles.

### 2.1 Terminal-first, not terminal-only

The terminal is the first client, but the torrent engine should not depend on terminal rendering. A future desktop UI, web UI, mobile controller, or automation API should be able to reuse the same backend.

### 2.2 Persistent engine

Closing the TUI must not terminate active torrents.

Torq should therefore use a small background process:

```text
              +--------------------+
              |     torq TUI       |
              +---------+----------+
                        |
              local authenticated API
                        |
+-------------+   +-----v------+   +-----------------+
| torq CLI    +--->   torqd    +---> libtorrent      |
+-------------+   |   daemon   |   | session         |
                  +-----+------+   +-----------------+
                        |
              +---------+----------+
              | SQLite / resume    |
              | config / logs      |
              +--------------------+
```

### 2.3 Use a mature BitTorrent engine

Do **not** implement the BitTorrent protocol from scratch for the MVP.

Use the Python bindings for **libtorrent** as the transfer engine. Torq owns:

- product logic;
- session configuration;
- persistence;
- daemon lifecycle;
- API;
- queue rules;
- search providers;
- CLI/TUI;
- security checks;
- packaging.

libtorrent owns low-level BitTorrent networking such as peer connections, trackers, DHT, metadata exchange, piece transfer, and protocol mechanics.

This keeps the main application Python while avoiding years of protocol-engine work.

### 2.4 Search must be provider-based

The search feature must not be hard-wired to one website.

Use a provider interface:

```python
class SearchProvider(Protocol):
    id: str
    name: str

    async def search(self, query: SearchQuery) -> list[SearchResult]: ...
    async def resolve(self, result: SearchResult) -> ResolvedTorrent: ...
    async def healthcheck(self) -> ProviderHealth: ...
```

Providers can then include:

- Pirate Bay-compatible provider;
- generic JSON/API provider;
- generic RSS provider;
- local `.torrent` directory provider;
- future community plugins.

### 2.5 Lawful-use and network-boundary behavior

BitTorrent itself is content-neutral. Torq should be built as a general-purpose torrent client and should not contain features whose purpose is to bypass access controls or site/network restrictions.

For search providers:

- do not ship rotating piracy-site mirrors;
- do not automatically bypass CAPTCHA, anti-bot systems, ISP blocks, or geographical restrictions;
- make provider endpoints configurable;
- allow providers to be disabled completely;
- make it clear that users are responsible for the legality of content they access or distribute.

This also improves engineering quality because site-specific evasion logic is inherently brittle.

---

## 3. Scope

## 3.1 MVP scope

The first production-worthy release should support:

1. libtorrent-backed downloads.
2. Magnet links.
3. Local `.torrent` files.
4. Remote `.torrent` URLs.
5. Persistent daemon.
6. SQLite torrent registry.
7. Resume data.
8. Basic download queue.
9. Pause/resume/remove.
10. Download/upload limits.
11. Global and per-torrent statistics.
12. File selection and priorities.
13. Trackers, DHT, PEX, and magnet metadata retrieval.
14. Search-provider architecture.
15. One Pirate Bay-compatible search adapter.
16. CLI commands.
17. Textual-based TUI.
18. Configuration file.
19. Logs and `torq doctor` diagnostics.
20. Linux, macOS, and Windows support where libtorrent bindings can be packaged reliably.

## 3.2 Explicit non-goals for MVP

Do not block the MVP on:

- writing a pure-Python BitTorrent implementation;
- a desktop GUI;
- a browser UI;
- remote internet-facing control;
- mobile apps;
- torrent creation;
- RSS auto-downloading;
- WebTorrent;
- built-in media playback;
- VPN management;
- automatic mirror rotation;
- CAPTCHA solving;
- tracker account automation;
- private-tracker credential storage;
- distributed Torq-to-Torq synchronization.

These can be considered after the torrent engine, daemon, CLI, and TUI are stable.

---

## 4. Recommended Technology Stack

### Core

- **Python:** 3.12+ target.
- **Torrent engine:** libtorrent Python bindings.
- **Async runtime:** `asyncio`.
- **TUI:** Textual.
- **CLI:** Click.
- **HTTP client:** `httpx`.
- **HTML parsing:** `selectolax` or Beautiful Soup; prefer `selectolax` if provider parsing becomes performance-sensitive.
- **Models / validation:** Pydantic.
- **Persistence:** SQLite.
- **Async SQLite layer:** `aiosqlite` or a thin repository using the standard `sqlite3` module in controlled worker threads.
- **Configuration paths:** `platformdirs`.
- **Configuration format:** TOML.
- **Structured logs:** standard `logging` initially; optionally `structlog` later.
- **Testing:** pytest + pytest-asyncio.
- **HTTP mocking:** respx.
- **Formatting/linting:** Ruff.
- **Type checking:** mypy or Pyright.
- **Packaging/project management:** `pyproject.toml`; `uv` recommended for development and lockfile management.

### Why `asyncio`

Torrent status polling, daemon requests, provider searches, HTTP requests, TUI updates, and event delivery are all heavily I/O-driven. An async application boundary prevents the UI from blocking while the engine or providers are working.

### Why Textual

Torq needs more than colored text. It needs:

- tables;
- sortable lists;
- keyboard shortcuts;
- dialogs;
- tabs;
- progress bars;
- responsive terminal layouts;
- background workers;
- screen navigation;
- automated UI testing.

A full TUI framework is therefore preferable to manually redrawing terminal output.

### Why Click

The non-interactive CLI should remain simple and stable even if the TUI changes. Click provides command groups, options, help generation, shell integration, and predictable CLI behavior.

---

## 5. High-Level Architecture

Torq should use six major layers.

```text
+---------------------------------------------------------+
|                   USER INTERFACES                       |
|                                                         |
|   Click CLI         Textual TUI        Future clients   |
+---------------------------+-----------------------------+
                            |
+---------------------------v-----------------------------+
|                     CLIENT SDK                          |
|   TorqClient / API models / event stream / exceptions  |
+---------------------------+-----------------------------+
                            |
                       Local API
                            |
+---------------------------v-----------------------------+
|                     TORQ DAEMON                         |
|                                                         |
| Command service    Torrent service     Search service   |
| Queue manager      Settings service    Event broker     |
+-------------+----------------+--------------------------+
              |                |
+-------------v-----+   +------v--------------------------+
| Torrent Adapter   |   | Search Provider Framework       |
| libtorrent        |   | TPB-compatible / plugins        |
+-------------+-----+   +---------------------------------+
              |
+-------------v-------------------------------------------+
|             PERSISTENCE / LOCAL STATE                   |
| SQLite | resume data | config | cache | logs            |
+---------------------------------------------------------+
```

The UI should **never access libtorrent directly**.

All torrent operations should go through a service interface. This prevents the UI, daemon implementation, and torrent engine from becoming inseparable.

---

## 6. Repository Structure

Recommended initial layout:

```text
torq/
├── PLAN.md
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── src/
│   └── torq/
│       ├── __init__.py
│       ├── __main__.py
│       ├── version.py
│       │
│       ├── cli/
│       │   ├── app.py
│       │   ├── common.py
│       │   ├── output.py
│       │   └── commands/
│       │       ├── add.py
│       │       ├── search.py
│       │       ├── list.py
│       │       ├── show.py
│       │       ├── pause.py
│       │       ├── resume.py
│       │       ├── remove.py
│       │       ├── files.py
│       │       ├── config.py
│       │       ├── daemon.py
│       │       └── doctor.py
│       │
│       ├── tui/
│       │   ├── app.py
│       │   ├── bindings.py
│       │   ├── widgets/
│       │   ├── screens/
│       │   │   ├── torrents.py
│       │   │   ├── torrent_details.py
│       │   │   ├── search.py
│       │   │   ├── add.py
│       │   │   ├── settings.py
│       │   │   └── logs.py
│       │   └── styles/
│       │       └── torq.tcss
│       │
│       ├── client/
│       │   ├── client.py
│       │   ├── events.py
│       │   └── errors.py
│       │
│       ├── daemon/
│       │   ├── app.py
│       │   ├── lifecycle.py
│       │   ├── pidfile.py
│       │   ├── api.py
│       │   ├── auth.py
│       │   └── events.py
│       │
│       ├── torrents/
│       │   ├── engine.py
│       │   ├── libtorrent_engine.py
│       │   ├── models.py
│       │   ├── service.py
│       │   ├── queue.py
│       │   ├── priorities.py
│       │   ├── metadata.py
│       │   ├── paths.py
│       │   └── resume.py
│       │
│       ├── search/
│       │   ├── models.py
│       │   ├── service.py
│       │   ├── registry.py
│       │   ├── ranking.py
│       │   ├── cache.py
│       │   └── providers/
│       │       ├── base.py
│       │       ├── piratebay.py
│       │       ├── local.py
│       │       └── generic_json.py
│       │
│       ├── storage/
│       │   ├── database.py
│       │   ├── migrations.py
│       │   └── repositories/
│       │       ├── torrents.py
│       │       ├── settings.py
│       │       └── searches.py
│       │
│       ├── config/
│       │   ├── models.py
│       │   ├── loader.py
│       │   └── defaults.py
│       │
│       └── util/
│           ├── formatting.py
│           ├── size.py
│           ├── magnet.py
│           ├── network.py
│           └── ids.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── tui/
│   └── fixtures/
│       ├── torrents/
│       └── providers/
│
├── scripts/
│   ├── dev-daemon.py
│   └── release.py
│
└── docs/
    ├── architecture.md
    ├── providers.md
    ├── configuration.md
    └── troubleshooting.md
```

---

## 7. Core Domain Models

Keep the application's models independent of libtorrent types.

### Torrent ID

Torq should expose a stable application identifier rather than libtorrent object references.

Preferred identity:

```text
BitTorrent v1: SHA-1 info hash
BitTorrent v2: SHA-256 info hash
Hybrid: persist both if available
```

For display, Torq can use a short ID such as the first 8–12 hexadecimal characters, provided ambiguous prefixes are rejected.

### Torrent model

```python
@dataclass
class Torrent:
    id: str
    name: str
    source_type: SourceType
    source: str | None
    save_path: Path
    state: TorrentState
    progress: float
    total_size: int | None
    downloaded: int
    uploaded: int
    download_rate: int
    upload_rate: int
    seeds: int
    peers: int
    ratio: float
    eta_seconds: int | None
    added_at: datetime
    completed_at: datetime | None
    queue_position: int | None
```

### Torrent states

Use Torq-owned states:

```text
METADATA
QUEUED
CHECKING
DOWNLOADING
STALLED_DOWNLOAD
PAUSED
COMPLETED
SEEDING
STALLED_UPLOAD
ERROR
REMOVED
```

Map libtorrent status values to these states in one adapter module.

### Search result

```python
@dataclass
class SearchResult:
    provider_id: str
    external_id: str | None
    name: str
    size_bytes: int | None
    seeders: int | None
    leechers: int | None
    uploaded_at: datetime | None
    category: str | None
    magnet_uri: str | None
    torrent_url: str | None
    details_url: str | None
    score: float = 0.0
```

Never pass raw provider dictionaries through the application.

---

## 8. Torrent Engine Abstraction

Define an engine protocol before writing the libtorrent implementation.

```python
class TorrentEngine(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def add_magnet(self, magnet: str, options: AddOptions) -> TorrentRef: ...
    async def add_torrent_file(self, path: Path, options: AddOptions) -> TorrentRef: ...

    async def pause(self, torrent_id: str) -> None: ...
    async def resume(self, torrent_id: str) -> None: ...
    async def remove(self, torrent_id: str, delete_data: bool = False) -> None: ...

    async def status(self, torrent_id: str) -> TorrentStatus: ...
    async def list(self) -> list[TorrentStatus]: ...

    async def set_file_priority(self, torrent_id: str, file_index: int, priority: int) -> None: ...
    async def set_limits(self, torrent_id: str, limits: TransferLimits) -> None: ...
    async def recheck(self, torrent_id: str) -> None: ...
```

Benefits:

- unit tests can use a fake engine;
- future engine replacement is possible;
- libtorrent-specific details stay isolated;
- UI code becomes straightforward.

---

## 9. libtorrent Integration

### 9.1 Session ownership

Only the daemon owns the libtorrent session.

The TUI and one-shot CLI commands should never create separate sessions when the daemon is available.

### 9.2 Session initialization

On startup:

1. load Torq configuration;
2. initialize SQLite;
3. initialize libtorrent session;
4. configure listen interfaces/ports;
5. configure DHT;
6. configure local peer discovery if enabled;
7. configure PEX;
8. configure encryption preferences;
9. apply global speed and connection limits;
10. restore torrents and resume data;
11. start the alert/event processing task;
12. start periodic state persistence.

### 9.3 Alerts

Use libtorrent's alert system rather than constantly polling every property.

Create one engine event loop responsible for:

- metadata received;
- torrent added;
- state changed;
- torrent finished;
- tracker warnings/errors;
- file errors;
- peer errors worth exposing;
- storage movement;
- resume data ready;
- pause/resume confirmations.

Translate libtorrent alerts into Torq events.

Example:

```text
Libtorrent alert
      |
      v
LibtorrentEngine
      |
      v
TorqEvent
      |
  +---+----------------+
  |                    |
SQLite updates      Event broker
                       |
                 +-----+-----+
                 |           |
                TUI         CLI/API
```

### 9.4 Resume data

Resume data is essential.

Persist it:

- periodically;
- on pause where useful;
- after meaningful state changes;
- during clean daemon shutdown;
- before updating the application if practical.

Use atomic writes:

```text
resume.tmp -> fsync -> rename -> resume.dat
```

Avoid corrupting the only state copy during a crash.

### 9.5 Metadata-only magnet phase

A magnet URI may initially contain only an info hash.

Torq should show:

```text
State: Fetching metadata
Name:  <pending metadata>
Size:  unknown
Files: unavailable
```

Once metadata arrives, update the database and emit a metadata event.

---

## 10. Download Lifecycle

### Add magnet

```text
User
 |
 v
parse + validate magnet
 |
 v
TorrentService.add()
 |
 v
check duplicate info hash
 |
 +---- duplicate ----> return existing torrent
 |
 v
engine.add_magnet()
 |
 v
persist torrent row
 |
 v
queue/download
```

### Add `.torrent` file

1. verify file exists;
2. enforce maximum metadata file size;
3. parse torrent metadata;
4. validate filenames/paths;
5. calculate/obtain info hash;
6. detect duplicates;
7. resolve download directory;
8. optionally present file-selection dialog;
9. add torrent;
10. persist state;
11. start according to queue rules.

### Add remote torrent URL

Treat remote `.torrent` fetching as a separate security-sensitive operation.

Requirements:

- only allow `http` and `https` by default;
- reject `file://`, `ftp://`, `data:`, and arbitrary schemes;
- apply connection and total timeout;
- cap response size;
- limit redirects;
- validate response as torrent metadata;
- protect against unsafe redirect targets where feasible;
- save metadata into Torq cache before adding.

---

## 11. Queue Manager

Create a Torq queue manager instead of exposing only libtorrent defaults.

Config:

```toml
[queue]
max_active_downloads = 3
max_active_seeds = 5
max_active_total = 8
completed_action = "seed"
```

The manager determines which torrents are:

- active;
- queued;
- paused by user;
- paused by queue;
- force-started.

User pause must be distinct from queue pause.

Otherwise a queue rebalance might incorrectly resume something the user deliberately paused.

---

## 12. Search Architecture

Search should be a first-class service, not UI scraping logic.

### Search flow

```text
SearchQuery
    |
    v
SearchService
    |
    +--> provider A ----+
    +--> provider B ----+--> normalize --> dedupe --> score --> return
    +--> provider C ----+
```

Provider calls should run concurrently with individual timeouts.

A broken provider must not break the entire search.

### Search query model

```python
class SearchQuery(BaseModel):
    text: str
    category: str | None = None
    min_seeders: int | None = None
    max_size: int | None = None
    sort: SearchSort = SearchSort.RELEVANCE
    limit: int = 50
```

### Result ranking

Initial scoring can combine:

```text
text relevance
+ availability/seeder score
+ metadata completeness
+ provider confidence
- duplicate penalty
```

Do not simply sort all results by seed count because that can produce poor semantic matches.

### Deduplication

Preferred keys, in order:

1. info hash extracted from magnet URI;
2. canonical torrent URL or provider ID;
3. normalized `(name, size)` fingerprint.

When multiple providers return the same info hash, merge provider metadata instead of showing duplicate rows.

---

## 13. Pirate Bay-Compatible Provider

Implement this as one plugin under the generic provider system.

### Requirements

- Provider ID: `piratebay`.
- Base endpoint configurable by user.
- No hard-coded mirror rotation.
- No CAPTCHA or anti-bot bypass logic.
- Health-check command.
- HTML/API parsing isolated from application logic.
- Parser fixtures checked into tests.
- Strict timeout.
- Friendly failure messages when markup changes.

Suggested configuration:

```toml
[search.providers.piratebay]
enabled = false
base_url = ""
timeout_seconds = 8
```

A provider may be disabled by default depending on distribution/legal requirements. The architecture should work either way.

### Adapter stages

```text
query
  -> build provider request
  -> fetch
  -> parse
  -> normalize SearchResult objects
  -> validate magnet/torrent links
  -> return
```

Do not let provider HTML selectors leak outside `providers/piratebay.py`.

### Failure behavior

Example:

```text
$ torq search "example"

2/3 providers responded.

WARN piratebay: provider response format was not recognized.
Run `torq provider test piratebay --verbose` for diagnostics.
```

Search still returns results from healthy providers.

---

## 14. Provider Plugin System

After built-in providers work, expose Python package entry points.

Potential entry-point group:

```toml
[project.entry-points."torq.search_providers"]
my_provider = "my_package.provider:Provider"
```

Torq can discover installed plugins at startup.

Provider metadata:

```python
@dataclass
class ProviderManifest:
    id: str
    name: str
    version: str
    author: str | None
    capabilities: set[ProviderCapability]
```

Capabilities may include:

```text
SEARCH
MAGNET_DIRECT
TORRENT_DOWNLOAD
DETAILS_LOOKUP
CATEGORY_FILTER
SORT_SEEDS
PAGINATION
```

Do not add dynamic plugin downloading in the first release. Plugins should be installed through normal Python package mechanisms.

---

## 15. Daemon Design

Executable/service name:

```text
torqd
```

or expose it through:

```text
torq daemon start
```

The latter is preferable for users even if an internal `torqd` entry point also exists.

### Responsibilities

The daemon owns:

- libtorrent session;
- queue manager;
- torrent registry;
- search service;
- configuration runtime state;
- database connection;
- resume persistence;
- local API;
- event stream;
- logs.

### Local API

Use a local-only HTTP API initially because it is cross-platform and easy to debug.

Default binding:

```text
127.0.0.1 only
```

Do not bind to `0.0.0.0` by default.

Suggested API root:

```text
http://127.0.0.1:<dynamic-or-configured-port>/api/v1
```

Require a random local authentication token stored with restrictive permissions.

### Suggested endpoints

```text
GET    /health
GET    /version

GET    /torrents
POST   /torrents
GET    /torrents/{id}
DELETE /torrents/{id}
POST   /torrents/{id}/pause
POST   /torrents/{id}/resume
POST   /torrents/{id}/recheck
GET    /torrents/{id}/files
PATCH  /torrents/{id}/files/{index}
PATCH  /torrents/{id}/limits

GET    /search
GET    /providers
POST   /providers/{id}/test

GET    /settings
PATCH  /settings

GET    /events
```

### Event delivery

For MVP, use one of:

- Server-Sent Events;
- WebSocket;
- short polling.

Prefer **Server-Sent Events** if all current event traffic is daemon -> client. It is simpler than a WebSocket while still supporting live updates.

### Daemon startup behavior

When a CLI command runs:

1. check daemon health;
2. if unavailable and auto-start is enabled, start daemon;
3. wait for readiness with a short bounded retry;
4. execute command;
5. leave daemon running.

Commands like `torq daemon stop` explicitly terminate it.

---

## 16. Persistence

Use SQLite as the source of application metadata.

### Suggested tables

#### torrents

```text
id
info_hash_v1
info_hash_v2
name
source_type
source
save_path
state
queue_position
added_at
completed_at
user_paused
auto_managed
metadata_path
resume_path
error_code
error_message
```

#### torrent_settings

```text
torrent_id
download_limit
upload_limit
seed_ratio_limit
seed_time_limit
sequential_download
```

#### search_history

```text
id
query
provider_filter
created_at
```

#### provider_state

```text
provider_id
enabled
last_success_at
last_error_at
last_error
```

#### schema_migrations

```text
version
applied_at
```

### Important rule

High-frequency values such as instantaneous transfer speed do not need to be written to SQLite every second.

Persist durable state, not every telemetry update.

---

## 17. Filesystem Layout

Use `platformdirs` and OS-standard application directories.

Conceptually:

```text
config/
    config.toml
    daemon-token

data/
    torq.db
    resume/
    metadata/
    cache/
    state/
logs/
    torq.log
```

Downloads default to the user's standard Downloads folder unless configured otherwise.

Never place the database or resume files inside the Python package directory.

---

## 18. Configuration

Example:

```toml
[torq]
auto_start_daemon = true
check_updates = true

[downloads]
default_path = "~/Downloads"
incomplete_path = ""
preallocate = false

[network]
listen_port = 0
random_port_on_start = false
dht = true
pex = true
lsd = true
upnp = true
nat_pmp = true

[limits]
download_bytes_per_second = 0
upload_bytes_per_second = 0
max_connections = 500

[queue]
max_active_downloads = 3
max_active_seeds = 5
max_active_total = 8

[seeding]
stop_at_ratio = 0
stop_after_minutes = 0

[search]
result_limit = 50
cache_ttl_seconds = 300

[search.providers.piratebay]
enabled = false
base_url = ""
timeout_seconds = 8

[ui]
refresh_ms = 750
confirm_delete_data = true
show_zero_speed = false
```

### Configuration precedence

Use:

```text
CLI option
  > environment variable
  > config.toml
  > application default
```

Document every environment variable using a `TORQ_` prefix.

---

## 19. CLI Specification

Primary executable:

```text
torq
```

### Main commands

```text
torq                          Launch TUI

torq add <source>             Add magnet, .torrent, or URL
torq search <query>           Search providers
torq list                     List torrents
torq show <id>                Detailed torrent status

torq pause <id...>
torq resume <id...>
torq remove <id...>
torq recheck <id>

torq files <id>
torq file-priority <id> <file> <priority>

torq limit download <value>
torq limit upload <value>

torq provider list
torq provider enable <name>
torq provider disable <name>
torq provider test <name>

torq config get [key]
torq config set <key> <value>
torq config path

torq daemon start
torq daemon stop
torq daemon restart
torq daemon status

torq doctor
torq version
```

### Useful aliases

```text
torq ls      -> torq list
torq rm      -> torq remove
torq dl      -> torq add
```

Do not introduce too many aliases until the canonical command names settle.

### Machine-readable output

All read-oriented commands should eventually support:

```text
--json
```

Example:

```bash
torq list --json
```

This turns Torq into a useful automation tool as well as a TUI.

---

## 20. TUI Design

### Main layout

```text
┌ Torq ──────────────────────────────────────────────────────────┐
│ ↓ 24.1 MB/s   ↑ 1.8 MB/s   DHT 438 nodes   6 active           │
├────────────────────────────────────────────────────────────────┤
│ All  Downloading  Seeding  Completed  Paused  Error           │
├────────────────────────────────────────────────────────────────┤
│ Name              Progress  Size   Seeds  Peers   Down    ETA  │
│ Linux ISO         ████ 42%  4.8G   126    18      24M     1m   │
│ Dataset           ████████  100%   9.2G   88     12       --   │
│ ...                                                            │
├────────────────────────────────────────────────────────────────┤
│ [Enter] Details [a] Add [s] Search [p] Pause [r] Resume [?]    │
└────────────────────────────────────────────────────────────────┘
```

### Screens

#### Torrent Dashboard

- active torrents;
- global rates;
- quick filters;
- sortable columns;
- keyboard actions.

#### Torrent Details

Tabs:

```text
Overview | Files | Peers | Trackers | Pieces | Log
```

MVP can defer the Pieces visualization if necessary.

#### Search

```text
Search: ____________________________________
Provider: [All v]   Sort: [Relevance v]

Name                         Size      Seeds  Peers  Source
...
```

Actions:

```text
Enter   details
D       download
Space   select multiple
S       change sort
P       provider filter
```

#### Add Torrent dialog

Input supports:

- paste magnet;
- type URL;
- local file path.

After metadata is known:

- choose destination;
- choose files;
- start paused;
- queue position;
- sequential download option if exposed.

#### Settings

Start with only frequently used settings. Editing the raw TOML remains an escape hatch.

### Keyboard design

Recommended global bindings:

```text
q        quit TUI only
Q        optional daemon/quit workflow
/        filter
s        search
+a / a   add
p        pause
r        resume
d        details
x        remove torrent
?        help
Ctrl+R   refresh
```

Destructive actions should require confirmation.

---

## 21. Search CLI UX

Interactive search mode:

```bash
torq search "query"
```

If stdout is a TTY, render a table and optionally let the user select a result.

Non-interactive examples:

```bash
torq search "query" --provider piratebay --limit 20

torq search "query" --sort seeds --json
```

Useful filters:

```text
--provider
--category
--min-seeds
--max-size
--sort relevance|seeds|size|date
--limit
```

Avoid overloading the first release with dozens of provider-specific filters.

---

## 22. Input Detection

`torq add VALUE` should automatically classify input.

Order:

1. starts with `magnet:?` -> magnet;
2. existing local path -> local torrent file;
3. `http://` or `https://` -> remote torrent metadata URL;
4. otherwise -> invalid source.

Do not guess that arbitrary text is a search query inside `torq add`; use `torq search` explicitly.

This keeps scripts predictable.

---

## 23. Magnet Parsing

Torq should parse magnet URIs itself for validation/display before passing them into libtorrent.

Extract where available:

- exact topic / info hash;
- display name;
- tracker URLs;
- web seeds;
- acceptable sources.

Support BitTorrent v1/v2-compatible magnet formats as exposed by the underlying engine.

Return clear validation errors rather than raw engine exceptions.

---

## 24. File Selection and Priorities

For multi-file torrents:

```text
Priority 0 = do not download
Priority 1 = low
Priority 4 = normal
Priority 7 = high
```

The exact mapping to libtorrent priorities belongs only in the adapter.

CLI:

```bash
torq files 4F2A91C8

torq file-priority 4F2A91C8 3 off

torq file-priority 4F2A91C8 7 high
```

TUI should support toggling files using Space and applying priorities in bulk.

---

## 25. Path and Filesystem Security

Torrent metadata contains filenames controlled by external data.

Torq must protect the filesystem.

Validate against:

- `../` traversal;
- absolute embedded paths;
- Windows drive prefixes;
- reserved device names where relevant;
- null bytes;
- invalid path separators;
- unexpected symlink behavior;
- collisions after path normalization.

All final paths must remain inside the selected torrent download root unless the torrent engine provides a deliberately supported safe mapping.

Deletion is particularly sensitive.

`torq remove --delete-data` should:

1. display target torrent;
2. clearly distinguish removing metadata from deleting payload files;
3. confirm interactively unless `--yes` is supplied;
4. ensure deletion paths belong to that torrent's managed save path.

---

## 26. Networking and Privacy Settings

Expose normal torrent-client network controls without making Torq responsible for external privacy infrastructure.

Possible settings:

- listen interface;
- listen port;
- global peer connection limit;
- per-torrent connection limit;
- upload slots;
- DHT on/off;
- PEX on/off;
- LSD on/off;
- UPnP/NAT-PMP on/off;
- proxy configuration if libtorrent supports the desired mode;
- protocol encryption preference;
- IP family preference.

Do not market normal BitTorrent encryption as anonymity.

---

## 27. Error Model

Create application-specific errors.

```text
TorqError
├── ConfigurationError
├── DaemonUnavailableError
├── AuthenticationError
├── TorrentError
│   ├── InvalidMagnetError
│   ├── InvalidTorrentFileError
│   ├── DuplicateTorrentError
│   └── TorrentNotFoundError
├── SearchError
│   ├── ProviderUnavailableError
│   ├── ProviderParseError
│   └── ProviderTimeoutError
└── StorageError
```

The CLI maps these to concise messages and stable exit codes.

Example:

```text
ERROR: No torrent matched ID 'a83f'.
Hint: run `torq list` to see active torrent IDs.
```

Do not dump Python tracebacks during normal user errors.

`--debug` may expose them.

---

## 28. Logging and Diagnostics

### Logs

Use rotating log files.

Levels:

```text
ERROR
WARNING
INFO
DEBUG
```

Never log the daemon API token.

Consider redacting sensitive URL query parameters.

### `torq doctor`

The command should check:

- Python version;
- Torq version;
- libtorrent import/version;
- config readability;
- data directory writability;
- database health;
- daemon status;
- daemon API authentication;
- download directory;
- available disk space;
- network listen status;
- provider configuration;
- provider health checks when explicitly requested.

Output should make bug reports dramatically easier.

---

## 29. Database and State Recovery

Design for crashes from day one.

On daemon startup:

1. acquire single-instance lock;
2. open database;
3. run migrations;
4. inspect registered torrents;
5. load metadata and resume data;
6. re-add torrents to libtorrent;
7. reconcile database state against engine state;
8. mark missing metadata/resume problems visibly;
9. continue downloads where possible.

If the previous process crashed, Torq may need piece verification. Present this as `CHECKING`, not as a frozen download.

---

## 30. Daemon Single-Instance Protection

Only one Torq daemon should manage a data directory.

Use:

- PID file;
- process verification;
- exclusive lock file;
- local API health check.

Do not rely solely on a PID file because stale PID files are common after crashes.

Support alternate profiles/data directories later for advanced users.

---

## 31. Performance Targets

Torq's Python layer should avoid becoming the transfer bottleneck.

Initial targets:

- TUI refresh: 500–1000 ms.
- CLI daemon request: perceived instant for local operations.
- Search provider timeout: independently configurable, approximately 5–10 seconds by default.
- Database writes: batch where practical.
- Status refresh: request summaries, not full peer/file lists every cycle.
- Thousands of peer events should not trigger thousands of UI redraws.

Use event coalescing:

```text
500 engine events
     -> internal updates
     -> one summarized UI refresh
```

---

## 32. Testing Strategy

Testing must be built into each milestone.

### 32.1 Unit tests

Test:

- magnet parsing;
- byte-size parsing/formatting;
- ETA formatting;
- search ranking;
- deduplication;
- provider HTML parsing;
- queue rules;
- config precedence;
- torrent state mapping;
- path validation;
- ID prefix resolution.

### 32.2 Provider parser tests

Never make ordinary parser tests depend on a live torrent index.

Store sanitized HTML/JSON fixtures:

```text
tests/fixtures/providers/piratebay/search_page.html
```

Then test deterministic parsing.

A separate opt-in integration test may check a configured endpoint, but it must not run in normal CI.

### 32.3 Torrent engine integration tests

Use controlled legal test payloads.

Create tiny local torrents or project-owned test fixtures and seed them from a local test peer where feasible.

Test:

- add torrent;
- magnet metadata resolution where practical;
- download completion;
- pause/resume;
- recheck;
- resume after daemon restart;
- file priority;
- remove without data;
- remove with data.

### 32.4 Daemon API tests

Start daemon against a temporary directory and temporary port.

Test:

- authentication;
- health;
- torrent CRUD;
- event stream;
- restart recovery;
- invalid requests;
- concurrent clients.

### 32.5 TUI tests

Use Textual's testing support for:

- launching screens;
- keyboard navigation;
- search dialog;
- torrent selection;
- pause/resume;
- destructive confirmation;
- daemon disconnect banner.

### 32.6 End-to-end smoke test

A release candidate should pass:

```text
install Torq
start daemon
add controlled torrent
observe progress
complete download
close and reopen TUI
verify persisted torrent
pause/resume
remove
stop daemon
```

---

## 33. CI Pipeline

GitHub Actions or equivalent:

```text
1. lint
2. format check
3. type check
4. unit tests
5. integration tests
6. TUI tests
7. build package
8. install built package
9. CLI smoke tests
```

Matrix:

```text
Linux   Python 3.12 / 3.13
macOS   Python 3.12 / 3.13
Windows Python 3.12 / 3.13
```

The supported matrix must ultimately reflect where the chosen libtorrent bindings can be distributed reliably.

That dependency deserves a dedicated packaging spike before Torq promises broad platform support.

---

## 34. Packaging and Installation

Desired user experience:

```bash
pipx install torq
```

or:

```bash
uv tool install torq
```

Then:

```bash
torq
```

### Console entry points

```toml
[project.scripts]
torq = "torq.cli.app:main"
torqd = "torq.daemon.app:main"
```

If exposing `torqd` is unnecessary to ordinary users, document `torq daemon ...` as the supported interface.

### libtorrent packaging spike

This is one of the most important technical risks.

Before building large amounts of UI, verify:

- installation from a clean Linux environment;
- clean macOS installation;
- clean Windows installation;
- compatibility with supported Python versions;
- whether wheels are available or a native build toolchain is required;
- whether Torq can publish self-contained platform artifacts later.

If Python package installation proves unreliable, investigate application bundles or platform-specific installers rather than replacing the entire engine immediately.

---

## 35. Release Strategy

Use semantic versioning.

Suggested sequence:

```text
0.1.0  Engine spike + add/list/pause/resume
0.2.0  Persistent daemon + SQLite + restart recovery
0.3.0  Search framework + first provider
0.4.0  Basic Textual TUI
0.5.0  Files/priorities/queue/settings
0.6.0  Cross-platform hardening + packaging
0.7.0  Plugin system + improved search
0.8.0  Performance and resilience pass
0.9.0  Release candidate
1.0.0  Stable CLI/API/config compatibility
```

Do not declare 1.0 until daemon restart/recovery and data deletion behavior have received significant testing.

---

# 36. Implementation Milestones

## Phase 0 — Technical Validation

**Goal:** Prove the core architecture before building product UI.

### Tasks

- [ ] Create repository.
- [ ] Add `pyproject.toml`.
- [ ] Configure `uv`.
- [ ] Configure Ruff.
- [ ] Configure type checker.
- [ ] Configure pytest.
- [ ] Verify libtorrent Python bindings on Linux.
- [ ] Verify macOS installation.
- [ ] Verify Windows installation.
- [ ] Write a 50–100 line experiment that creates a libtorrent session.
- [ ] Add a controlled `.torrent` test fixture.
- [ ] Download it successfully.
- [ ] Add a magnet URI and receive metadata.
- [ ] Save resume data.
- [ ] Stop process.
- [ ] Restore resume data.
- [ ] Confirm transfer resumes correctly.
- [ ] Prototype libtorrent alert handling.
- [ ] Document binding/install limitations.

### Exit criteria

A standalone Python spike can add, transfer, stop, restore, and resume a torrent reliably.

---

## Phase 1 — Core Torrent Service

**Goal:** Build a UI-independent download core.

### Tasks

- [ ] Define domain models.
- [ ] Define `TorrentEngine` protocol.
- [ ] Implement `LibtorrentEngine`.
- [ ] Implement magnet validation.
- [ ] Implement `.torrent` metadata validation.
- [ ] Implement add options.
- [ ] Implement pause.
- [ ] Implement resume.
- [ ] Implement remove.
- [ ] Implement recheck.
- [ ] Implement status mapping.
- [ ] Implement file list.
- [ ] Implement file priority.
- [ ] Implement global limits.
- [ ] Implement per-torrent limits.
- [ ] Translate alerts to Torq events.
- [ ] Add fake engine for tests.
- [ ] Add unit tests.

### Exit criteria

The torrent service can be controlled entirely through Python tests without a TUI.

---

## Phase 2 — Persistence and Daemon

**Goal:** Make Torq persistent.

### Tasks

- [ ] Implement application directories.
- [ ] Add SQLite schema.
- [ ] Add migration mechanism.
- [ ] Add torrent repository.
- [ ] Add resume store.
- [ ] Add metadata cache.
- [ ] Add config loader.
- [ ] Implement daemon.
- [ ] Add single-instance locking.
- [ ] Add daemon PID/state handling.
- [ ] Add local API token.
- [ ] Bind API to loopback only.
- [ ] Implement health endpoint.
- [ ] Implement torrent endpoints.
- [ ] Implement event stream.
- [ ] Add daemon auto-start.
- [ ] Implement clean shutdown.
- [ ] Implement crash/restart reconciliation.
- [ ] Add daemon integration tests.

### Exit criteria

A download continues after the CLI exits and is restored after daemon restart.

---

## Phase 3 — Scriptable CLI

**Goal:** Make Torq useful before the TUI exists.

### Tasks

- [ ] Implement `torq add`.
- [ ] Implement source auto-detection.
- [ ] Implement `torq list`.
- [ ] Implement `torq show`.
- [ ] Implement pause/resume.
- [ ] Implement remove.
- [ ] Implement recheck.
- [ ] Implement files command.
- [ ] Implement file priority command.
- [ ] Implement limits.
- [ ] Implement daemon commands.
- [ ] Implement configuration commands.
- [ ] Add `--json` output to read commands.
- [ ] Define stable exit codes.
- [ ] Add shell completion if straightforward.
- [ ] Implement `torq doctor`.

### Exit criteria

Torq is a usable headless torrent client from shell scripts.

---

## Phase 4 — Search System

**Goal:** Search and resolve torrent metadata through providers.

### Tasks

- [ ] Define provider protocol.
- [ ] Define search models.
- [ ] Implement provider registry.
- [ ] Implement concurrent search.
- [ ] Implement timeouts.
- [ ] Implement partial-failure handling.
- [ ] Implement result normalization.
- [ ] Implement deduplication.
- [ ] Implement ranking.
- [ ] Implement search cache.
- [ ] Implement Pirate Bay-compatible provider.
- [ ] Store provider fixtures.
- [ ] Write parser tests.
- [ ] Add provider health checks.
- [ ] Implement `torq search`.
- [ ] Enable downloading a selected result.
- [ ] Implement provider enable/disable/configuration.

### Exit criteria

A user can search configured providers and add a selected result to the download daemon without manually copying the magnet URI.

---

## Phase 5 — Textual TUI

**Goal:** Deliver the qBittorrent-like terminal experience.

### Tasks

- [ ] Create application shell.
- [ ] Add daemon connection manager.
- [ ] Add status header.
- [ ] Add torrent table.
- [ ] Add filters.
- [ ] Add sorting.
- [ ] Add torrent details screen.
- [ ] Add files tab.
- [ ] Add trackers tab.
- [ ] Add peers tab.
- [ ] Add add-torrent dialog.
- [ ] Add search screen.
- [ ] Add settings screen.
- [ ] Add command palette if useful.
- [ ] Add keyboard help.
- [ ] Add pause/resume/remove actions.
- [ ] Add delete-data confirmation.
- [ ] Add notifications/toasts.
- [ ] Add daemon-disconnected state.
- [ ] Add TUI test suite.

### Exit criteria

The TUI can handle the complete normal download workflow without requiring CLI fallback.

---

## Phase 6 — Queueing, Seeding, and Advanced Controls

**Goal:** Reach feature depth expected from a real download manager.

### Tasks

- [ ] Implement queue manager.
- [ ] Active-download limits.
- [ ] Active-seed limits.
- [ ] Force-start.
- [ ] Move queue position.
- [ ] Ratio-based seeding policy.
- [ ] Time-based seeding policy.
- [ ] Torrent categories/tags.
- [ ] Download destination rules.
- [ ] Sequential download if retained.
- [ ] Tracker management.
- [ ] Move torrent data.
- [ ] Better peer/connection statistics.
- [ ] Free-space warnings.

### Exit criteria

Torq is suitable for long-running multi-torrent use rather than only one-off downloads.

---

## Phase 7 — Plugin and Distribution Hardening

**Goal:** Make Torq extensible and easy to install.

### Tasks

- [ ] Implement search-provider entry points.
- [ ] Validate third-party provider manifests.
- [ ] Add provider documentation.
- [ ] Add package build CI.
- [ ] Add clean-install smoke tests.
- [ ] Produce Windows installation instructions/artifacts.
- [ ] Produce macOS installation instructions/artifacts.
- [ ] Produce Linux installation instructions/artifacts.
- [ ] Add changelog automation.
- [ ] Add release signing/checksums where appropriate.
- [ ] Add compatibility policy.
- [ ] Add security reporting process.

### Exit criteria

A new user can install Torq on a supported OS and a developer can install an external search provider without editing Torq source code.

---

## Phase 8 — 1.0 Stabilization

**Goal:** Freeze core behavior and eliminate dangerous edge cases.

### Focus

- [ ] crash recovery;
- [ ] database migrations;
- [ ] resume reliability;
- [ ] very large torrents;
- [ ] torrents with thousands of files;
- [ ] path edge cases;
- [ ] disk-full behavior;
- [ ] network interruption;
- [ ] malformed magnets;
- [ ] malformed `.torrent` files;
- [ ] provider failures;
- [ ] daemon upgrade/restart;
- [ ] Windows filesystem behavior;
- [ ] delete-data safety;
- [ ] terminal resize behavior;
- [ ] accessibility/readability;
- [ ] documentation.

### Exit criteria

No known issue can reasonably cause Torq to delete unrelated user data, corrupt its torrent registry, or silently lose resumable download state.

---

# 37. Detailed MVP User Stories

## Torrent input

- [ ] As a user, I can paste a magnet URI and start downloading.
- [ ] As a user, I can pass a `.torrent` path.
- [ ] As a user, I can pass an HTTP(S) `.torrent` URL.
- [ ] As a user, I get an understandable error for malformed input.
- [ ] As a user, duplicate torrents are detected.

## Download management

- [ ] I can see current progress.
- [ ] I can see download/upload speed.
- [ ] I can see seed/peer counts.
- [ ] I can pause and resume.
- [ ] I can remove a torrent without deleting files.
- [ ] I can explicitly remove a torrent and delete its files.
- [ ] I can choose individual files.
- [ ] I can prioritize files.
- [ ] I can set speed limits.

## Persistence

- [ ] Downloads survive closing the TUI.
- [ ] Downloads survive daemon restart.
- [ ] Completed torrents remain in history/state.
- [ ] Paused torrents remain paused.

## Search

- [ ] I can search a configured provider.
- [ ] I can search all enabled providers.
- [ ] I can sort by relevance/seeds/size/date.
- [ ] I can inspect result metadata.
- [ ] I can download a result.
- [ ] One failed provider does not break other results.

## Operations

- [ ] I can diagnose common installation problems.
- [ ] I can find the config path.
- [ ] I can find the log path.
- [ ] I can stop/restart the daemon.
- [ ] CLI output works in scripts.

---

# 38. Security Review Checklist

Before 1.0, explicitly review:

### Filesystem

- [ ] path traversal;
- [ ] absolute paths in metadata;
- [ ] symlink handling;
- [ ] deletion boundaries;
- [ ] file overwrite behavior;
- [ ] temporary file permissions.

### Daemon

- [ ] loopback-only default;
- [ ] random API token;
- [ ] token permissions;
- [ ] CSRF assumptions if any browser client is ever added;
- [ ] request size limits;
- [ ] malformed request handling;
- [ ] no token in logs.

### Remote torrent URLs

- [ ] scheme allowlist;
- [ ] redirect limit;
- [ ] response size cap;
- [ ] timeout;
- [ ] content validation;
- [ ] unsafe local/network target review.

### Search providers

- [ ] sanitized terminal text;
- [ ] no shell execution;
- [ ] URL validation;
- [ ] response size limit;
- [ ] timeout;
- [ ] parser failures contained;
- [ ] no automatic access-control bypass logic.

### Dependency chain

- [ ] lock dependencies;
- [ ] vulnerability scanning;
- [ ] minimized runtime dependencies;
- [ ] reproducible release process where practical.

---

# 39. Important Engineering Risks

## Risk 1 — libtorrent Python distribution

**Impact:** High.  
**Reason:** Native bindings can complicate installation across OS/Python combinations.  
**Mitigation:** Make this Phase 0's first technical spike and automate clean-install testing early.

## Risk 2 — Search provider breakage

**Impact:** Medium/high.  
**Reason:** Site markup/endpoints can change.  
**Mitigation:** Provider isolation, fixtures, health checks, multiple providers, no business logic coupled to HTML.

## Risk 3 — Daemon/client race conditions

**Impact:** High.  
**Mitigation:** One owner of torrent state, explicit event model, repository transactions, bounded API behavior.

## Risk 4 — Resume-state corruption

**Impact:** High.  
**Mitigation:** Atomic persistence, shutdown hooks, backups/versioning where appropriate, integration restart tests.

## Risk 5 — Unsafe deletion/path handling

**Impact:** Critical.  
**Mitigation:** canonical path checks, managed-root enforcement, confirmation, extensive path tests.

## Risk 6 — UI performance with many torrents

**Impact:** Medium.  
**Mitigation:** summarize data, virtualized tables where supported, update only changed rows, rate-limit redraws.

## Risk 7 — Scope explosion

**Impact:** High.  
**Mitigation:** CLI before TUI; TUI before advanced features; plugin API only after built-in provider interface stabilizes.

---

# 40. Recommended Development Order

The most efficient build order is:

```text
libtorrent spike
    ↓
engine abstraction
    ↓
torrent service
    ↓
resume persistence
    ↓
daemon
    ↓
local API + client
    ↓
CLI
    ↓
search provider framework
    ↓
first search provider
    ↓
Textual TUI
    ↓
queue / advanced features
    ↓
plugin system
    ↓
packaging hardening
```

Do **not** build the polished TUI first.

The highest-risk parts of Torq are the native torrent-engine binding, daemon lifecycle, state recovery, and safe filesystem behavior. Validate those before investing heavily in UI.

---

# 41. First 20 Implementation Tickets

A practical first sprint/backlog:

1. `chore: initialize Python package and tooling`
2. `spike: validate libtorrent bindings on Linux/macOS/Windows`
3. `spike: add and download local test torrent`
4. `spike: persist and restore libtorrent resume data`
5. `core: define TorrentEngine interface`
6. `core: implement LibtorrentEngine startup/shutdown`
7. `core: implement torrent domain models`
8. `core: implement magnet parser and validator`
9. `core: implement add magnet`
10. `core: implement add torrent file`
11. `core: implement status/list`
12. `core: implement pause/resume/remove`
13. `events: translate libtorrent alerts to Torq events`
14. `storage: initialize SQLite schema and migrations`
15. `storage: persist torrent registry`
16. `storage: implement atomic resume store`
17. `daemon: implement single-instance lifecycle`
18. `daemon: implement loopback health API`
19. `client: implement TorqClient`
20. `cli: implement torq add/list/pause/resume`

At ticket 20, Torq should already be demonstrably useful.

---

# 42. Post-MVP Feature Ideas

After a stable core exists, consider:

### Search and automation

- RSS provider.
- Saved searches.
- Search subscriptions.
- Notification rules.
- Automatic category/save-path rules.
- Search aliases.

### Torrent management

- labels/categories;
- automatic queue policies;
- share-ratio targets;
- scheduled speed limits;
- alternate speed profile;
- relocate completed files;
- torrent creator;
- tracker editing;
- bulk actions.

### Interfaces

- read-only web dashboard;
- authenticated remote controller;
- desktop frontend using the same daemon API;
- JSON-RPC or SDK for external automation;
- shell completion;
- system tray companion.

### Terminal UX

- command palette;
- fuzzy torrent finder;
- graphs for transfer history;
- compact mode;
- themes;
- piece visualization;
- network diagnostics screen;
- live event/log panel.

### Extensibility

- search-provider SDK;
- lifecycle hooks;
- notification plugins;
- post-completion commands with explicit opt-in and secure argument handling.

---

# 43. 1.0 Acceptance Criteria

Torq 1.0 is ready when all of the following are true:

### Installation

- [ ] Supported platforms have documented, repeatable installation.
- [ ] `torq --version` works immediately after installation.
- [ ] `torq doctor` identifies common dependency problems.

### Transfer engine

- [ ] Magnet links work.
- [ ] `.torrent` files work.
- [ ] Remote torrent metadata URLs work.
- [ ] DHT/tracker-based torrents work according to libtorrent capabilities.
- [ ] Pause/resume works.
- [ ] File selection works.
- [ ] Limits work.
- [ ] Resume across restart works reliably.

### Daemon

- [ ] One daemon owns one state directory.
- [ ] Closing TUI does not stop downloads.
- [ ] Unexpected daemon termination does not destroy torrent registry state.
- [ ] Local API is not externally exposed by default.

### Search

- [ ] Provider architecture is stable.
- [ ] At least one index provider is usable when configured.
- [ ] Provider failures are isolated.
- [ ] Search results can be sent directly to the torrent engine.

### CLI

- [ ] Core management operations have non-interactive commands.
- [ ] Read operations support JSON where promised.
- [ ] Errors have stable non-zero exit codes.

### TUI

- [ ] User can add, search, monitor, pause, resume, remove, and inspect torrents.
- [ ] Keyboard help is built in.
- [ ] Terminal resizing does not break core screens.
- [ ] Daemon disconnect is visible and recoverable.

### Safety

- [ ] Torrent paths cannot escape intended managed locations through straightforward malicious metadata.
- [ ] Delete-data workflow has explicit safeguards.
- [ ] Remote torrent fetching has time/size/scheme restrictions.
- [ ] API credentials are not logged.

### Quality

- [ ] CI passes on supported platforms.
- [ ] Unit, integration, daemon, and TUI tests exist.
- [ ] README has quick start.
- [ ] Architecture is documented.
- [ ] Configuration is documented.
- [ ] Provider-development guide exists.

---

# 44. Final Recommended MVP Boundary

The strongest first public version of Torq is **not** “every qBittorrent feature in a terminal.”

It is this coherent product:

```text
A persistent Python torrent daemon powered by libtorrent,
controlled through a clean CLI and a Textual TUI,
with magnet/.torrent support, robust resume behavior,
and a pluggable multi-provider torrent search system.
```

If this foundation is clean, Torq can later grow into desktop, web, automation, and remote-control use cases without replacing its architecture.

The implementation priority should therefore remain:

> **transfer correctness -> persistence -> daemon safety -> CLI -> search -> TUI polish -> extensibility.**

That order minimizes technical risk while producing a usable application early in development.

---

# 45. Sliced Implementation Backlog

This section converts PLAN §36 (Phases 0–8) and §41 (First 20 Tickets) into small, individually committable slices. Each slice ends in something runnable + testable. Bug checks at the markers below are full review sweeps — not just "pytest passes".

## Slice ledger

| #   | Slice                                          | Phase  | Bug check        |
| --- | ---------------------------------------------- | ------ | ---------------- |
| 0.1 | Repo bootstrap (package, tooling, CI lint)     | Phase 0 |                  |
| 0.2 | libtorrent spike (Linux)                       | Phase 0 |                  |
| 0.3 | libtorrent spike (Windows + macOS)             | Phase 0 |                  |
| 0.4 | Controlled test-torrent fixture                | Phase 0 |                  |
| 0.5 | `TorrentEngine` interface + domain models      | Phase 1 |                  |
| 0.6 | Magnet parser + validator                      | Phase 1 |                  |
| 0.7 | `.torrent` file validation                     | Phase 1 |                  |
| 0.8 | `LibtorrentEngine`: add + status + list        | Phase 1 |                  |
| 0.9 | `LibtorrentEngine`: pause/resume/remove/recheck | Phase 1 | ★ Bug check 1   |
| 0.10 | `LibtorrentEngine`: file priority + limits    | Phase 1 |                  |
| 0.11 | libtorrent alert → Torq events                | Phase 1 |                  |
| 0.12 | App directories + TOML config loader           | Phase 2 |                  |
| 0.13 | SQLite schema + migrations                    | Phase 2 |                  |
| 0.14 | Atomic resume store                           | Phase 2 |                  |
| 0.15 | Daemon lifecycle + single-instance             | Phase 2 |                  |
| 0.16 | Local HTTP API (loopback only)                | Phase 2 | ★ Bug check 2   |
| 0.17 | Torrent CRUD endpoints                        | Phase 2 |                  |
| 0.18 | SSE event stream                              | Phase 2 |                  |
| 0.19 | Auto-start daemon + readiness handshake       | Phase 2 |                  |
| 0.20 | `TorqClient` SDK                              | Phase 2 |                  |
| 0.21 | CLI: `add` with input detection               | Phase 3 |                  |
| 0.22 | CLI: `list`, `show`, `pause`, `resume`, `remove`, `recheck` | Phase 3 |       |
| 0.23 | CLI: `files`, `file-priority`, `limit`        | Phase 3 |                  |
| 0.24 | CLI: `daemon` subcommands                     | Phase 3 |                  |
| 0.25 | CLI: `config`, `provider`, `version`, `doctor` | Phase 3 | ★ Bug check 3   |
| 0.26 | Search models + `SearchProvider` protocol     | Phase 4 |                  |
| 0.27 | Search service: fan-out, dedup, ranking       | Phase 4 |                  |
| 0.28 | Search cache (TTL)                           | Phase 4 |                  |
| 0.29 | Pirate Bay-compatible provider                | Phase 4 |                  |
| 0.30 | Provider fixtures + parser tests              | Phase 4 |                  |
| 0.31 | Local + generic-JSON providers                | Phase 4 |                  |
| 0.32 | `torq search` CLI                            | Phase 4 |                  |
| 0.33 | Textual TUI shell                             | Phase 5 |                  |
| 0.34 | Torrent dashboard                             | Phase 5 |                  |
| 0.35 | Torrent details screen                        | Phase 5 |                  |
| 0.36 | Add-torrent dialog + Search screen            | Phase 5 |                  |
| 0.37 | Settings screen + daemon-disconnect banner    | Phase 5 |                  |
| 0.38 | Queue manager                                 | Phase 6 |                  |
| 0.39 | Seeding policies + tags/categories            | Phase 6 | ★ Bug check 4   |
| 0.40 | Path + filesystem security hardening          | Phase 6 |                  |
| 0.41 | Plugin entry points                           | Phase 7 |                  |
| 0.42 | Packaging hardening                           | Phase 7 |                  |
| 0.43 | 1.0 stabilization pass                        | Phase 8 | ★ Bug check 5 (final) |

## Bug-check focus by checkpoint

| Checkpoint | After slice | Focus                                                                                                       |
| ---------- | ----------- | ----------------------------------------------------------------------------------------------------------- |
| 1          | 0.9         | Engine basics: ID stability, pause/resume idempotency, remove-with-data correctness on a real libtorrent session. |
| 2          | 0.16        | Daemon lifecycle: stale PID handling, double-start prevention, crash during API call, token leakage in logs. |
| 3          | 0.25        | CLI ergonomics: input detection, exit codes, `--json` stability, `torq doctor` accuracy.                    |
| 4          | 0.39        | Long-running: queue starvation, ratio loop, malformed tracker announcements, large-torrent metadata fetch.   |
| 5          | 0.43        | 1.0: delete-data safety, path traversal, crash mid-write, resume restoration, daemon upgrade, terminal resize. |

Each bug check = targeted regression tests + a review of the diffs added since the last checkpoint, with anything suspicious turned into a ticket before moving on.

## CI/CD workflows

Six GitHub Actions workflows plus Dependabot, all under `.github/`:

1. **`lint.yml`** — Ruff (`check` + `format --check`) + mypy strict on `src/torq/`. Caches uv store.
2. **`unit-tests.yml`** — Matrix: Ubuntu / macOS / Windows × Python 3.12 / 3.13. Runs `tests/unit`. Uploads junit XML.
3. **`integration-tests.yml`** — Same matrix, runs `tests/integration` + `tests/tui` (Textual `pilot`). Per-OS libtorrent install. Live provider hits gated by `RUN_LIVE_PROVIDER_TESTS` secret.
4. **`build.yml`** — `uv build`, verifies `torq`/`torqd` entry points and `--help` on the built wheel artifact.
5. **`smoke.yml`** — Runs after `build.yml`: install the built wheel in a clean venv, exercise `torq --version`, daemon start, add fixture, list, pause, resume, remove, `doctor`, daemon stop.
6. **`release.yml`** — Tag-triggered (`v*`); builds sdist + wheels per platform; generates SBOM (`cyclonedx-py`), SHA256SUMS, signs with cosign where keys are configured; publishes to PyPI via trusted publishing; attaches artifacts to the GitHub Release.

Cross-cutting:

- **Dependabot** (`dependabot.yml`) — weekly updates for `uv` lockfile and GitHub Actions versions.
- **CodeQL** (`codeql.yml`) — Python security analysis on every push/PR.
- **Concurrency** — group key on PR/branch so superseded runs auto-cancel.
- **Permissions** — default `GITHUB_TOKEN` to read-only; elevate only where needed.
- **Caching** — uv + pip caches keyed by hash of `pyproject.toml`/`uv.lock`.
- **Branch protection** — `lint` + `unit-tests` required to merge; `integration` required on `main`.

# Contributing to Torq

Thanks for your interest in Torq. The project is pre-alpha; the priority is
landing the slice backlog in [PLAN.md](PLAN.md) §45 in order.

## Development setup

Torq targets **Python 3.12+** and uses [uv](https://docs.astral.sh/uv/) for
project management.

```bash
git clone https://github.com/<owner>/torq
cd torq
uv sync --all-extras
uv run torq --version
```

## Code style

- **Formatter / linter:** [Ruff](https://docs.astral.sh/ruff/) — `ruff format`
  and `ruff check`. Config in `pyproject.toml`.
- **Type checker:** mypy in strict mode on `src/torq/`.
- **Line length:** 100. Double-quoted strings.

Run before sending a PR:

```bash
uv run ruff format --check
uv run ruff check
uv run mypy src/torq
uv run pytest
```

## Slice workflow

1. Pick a slice from PLAN.md §45. Mark it as in-progress.
2. Implement the smallest useful change. Prefer small, focused commits.
3. Add or update tests. Keep coverage proportional to risk (engine, daemon,
   and delete-data paths get the most attention).
4. Run the full local QA loop above.
5. Open a PR with a description tied to the slice number.

Do **not** bundle multiple slices into one PR. Reviewers should be able to
read each slice as a coherent unit.

## Commit messages

Use a short prefix followed by a colon:

- `chore:` — tooling, packaging, docs
- `spike:` — investigative throwaway work
- `core:` — engine, models, libtorrent adapter
- `events:` — alert/event translation
- `storage:` — SQLite, repositories, resume
- `daemon:` — daemon lifecycle, local API
- `client:` — TorqClient SDK
- `cli:` — Click commands
- `search:` — provider framework and providers
- `tui:` — Textual screens and widgets
- `test:` — test-only changes
- `fix:` — bug fixes
- `docs:` — documentation

Example: `core: implement add magnet for LibtorrentEngine (slice 0.9)`.

## Testing

- `tests/unit/` — pure unit tests; must run in CI on every PR.
- `tests/integration/` — touches the engine or daemon; may need a libtorrent
  fixture.
- `tests/tui/` — Textual `pilot` tests.
- `tests/e2e/` — full lifecycle smoke; opt-in.

Provider parser tests must rely on checked-in HTML/JSON fixtures, not live
indexes. Live provider hits are opt-in via the `RUN_LIVE_PROVIDER_TESTS`
secret.

## Conduct

Be respectful. Assume good faith. Feedback is about code, not people.
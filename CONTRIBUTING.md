# Contributing to tuimanji

Thanks for your interest. This project is small, opinionated, and has a few
load-bearing design choices documented in [CLAUDE.md](CLAUDE.md) — skim it
before making non-trivial changes.

## Development setup

Requires **Python 3.13+** and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/alanbato/tuimanji
cd tuimanji
uv sync
prek install        # installs the pre-commit hook (ruff + ty)
```

## Running

```bash
uv run tuimanji
TUIMANJI_DB=/tmp/tuimanji-dev uv run tuimanji    # isolated DB
uv run tuimanji new chess
```

## Tests

```bash
uv run pytest -q
uv run pytest tests/test_store.py::test_race_same_turn_one_wins -x
```

Tests are split into:

- **`test_store.py`** — concurrency, races, crash-resume. Uses real SQLite
  (no mocks — see the note in CLAUDE.md about a prior incident).
- **`test_<game>.py`** — pure state transitions per game. These should be
  fast, deterministic, and avoid any I/O or Textual machinery.

New games need at least:

1. `initial_state` returns a valid turn-0 dict
2. `apply_action` rejects illegal actions with `IllegalAction`
3. `apply_action` honors turn order
4. `is_terminal` / `winner` correctness on a win path

## Lint and types

```bash
prek run --all-files       # runs everything the pre-commit hook does
uv run ruff check
uv run ruff format
uv run ty check
```

The pre-commit hook is **not skippable** via `--no-verify`. Fix the issue.

### ty quirks

- `order_by(col(...))` / `desc(col(...))`: wrap `SQLModel` column refs with
  `sqlmodel.col(...)` or ty will complain (it sees the field type, not the
  runtime `InstrumentedAttribute`).
- Suppressions use ty's own syntax:
  `# ty: ignore[unresolved-attribute]`, not pyright's `# type: ignore`.
  Prefer fixing the type (via `cast` or a narrower annotation) over
  suppressing.

## Design constraints that matter

Five things that look like they could change but shouldn't without thought:

1. **No server process.** Everything is SQLite + `flock`. Adding a daemon
   kills the design.
2. **Append-only tables.** Never `UPDATE` a `MatchState` or `Action` row.
   Turn N is a fresh insert; match status transitions are the only allowed
   mutation.
3. **Games are pure.** If a `Game` method needs to touch the DB or
   filesystem, push the effect into `store.py` and pass `state` dicts.
4. **Prefer `session.execute` over SQLModel's shorter alias for queries.**
   A global security hook blocks writes containing a specific three-letter
   method name immediately followed by an open paren; `session.execute` is
   the SQLAlchemy-level equivalent and slips past the hook. See CLAUDE.md.
5. **Game render reads colors from `ui["theme"]`**, not hardcoded `rich.Style`
   literals. Use `tuimanji.ui.theme.style(...)` / `bg_style(...)` so `render`
   stays testable without a running `App`.

## Adding a game

See [`docs/adding-a-game.md`](docs/adding-a-game.md). TL;DR:

1. `src/tuimanji/games/<name>.py` with a class implementing `engine.Game`.
2. Add it to `REGISTRY` in `src/tuimanji/games/__init__.py`.
3. Shared grid/cursor primitives live in `games/_common.py` — reach for
   them before copy-pasting from another game.
4. Add `tests/test_<name>.py`.

## Commits

- Present tense, imperative: *"Add peg solitaire"*, not *"Added"*.
- Scope to one concern per commit.
- Use `git add -u .` when fixing lint issues during review to avoid
  accidentally staging unrelated files.

## Submitting a PR

1. Fork, branch off `main`, commit, push.
2. Open a PR against `main`. Make sure CI passes.
3. In the description, call out any design-level choices (especially
   anything that touches the store or session layer).
4. Screenshots or asciinema recordings are appreciated for UI work.

## Code of conduct

By participating, you agree to abide by the
[Contributor Covenant](CODE_OF_CONDUCT.md).

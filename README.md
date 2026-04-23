# tuimanji

[![PyPI](https://img.shields.io/pypi/v/tuimanji.svg)](https://pypi.org/project/tuimanji/)
[![Python](https://img.shields.io/pypi/pyversions/tuimanji.svg)](https://pypi.org/project/tuimanji/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![CI](https://github.com/alanbato/tuimanji/actions/workflows/ci.yml/badge.svg)](https://github.com/alanbato/tuimanji/actions/workflows/ci.yml)

> A **pubnix-local turn-based multiplayer TUI.** No server. No accounts. Just
> log in to the same box as your friend and play something.

Tuimanji bundles nine turn-based games — Tic-Tac-Toe, Connect 4, Reversi,
Chess, Checkers, Battleship, Crazy Eights, Peg Solitaire, and the Royal Game
of Ur — behind a single Textual terminal UI. Matches live in a shared SQLite
database; clients coordinate via file locks and append-only writes. It's
designed for [pubnix](https://tildeverse.org/) boxes, shared servers, and
old-school SSH shenanigans.

## Why no server?

Because everything you need to synchronize turn-based games is already on the
box: a filesystem, a SQLite binary, and `flock(2)`. Running a daemon to
marshal moves would be more infrastructure to break. Instead:

- **State lives in `tuimanji.db`** — one file under `$TUIMANJI_DB`, WAL mode,
  `PRAGMA busy_timeout=5000`.
- **Writes are append-only.** Each turn is a new row; nothing is ever
  updated. Replay, spectating, and crash-resume fall out for free.
- **Concurrency is layered.** The app checks "is it your turn?"; SQLite's
  `BEGIN IMMEDIATE` serializes writers; a `(match_id, turn)` unique
  constraint catches anything that slips through.
- **Identity is a session slot.** `flock`ing
  `$TUIMANJI_DB/.sessions/<user>/N.lock` lets two terminals for the same
  unix user claim distinct player ids (`user`, `user#2`, …) — great for
  local testing, still sane for shared hosts.

## Install

```bash
# one-shot run
uv tool run tuimanji

# persistent install
uv tool install tuimanji
# or
pipx install tuimanji
# or
pip install --user tuimanji
```

Requires Python 3.13+ and a terminal that speaks 256 colors.

## Run

```bash
tuimanji                # open the lobby
tuimanji new chess      # create a new match + jump to its waiting room
tuimanji join a1b2c3d4  # join (or rejoin) an existing match
tuimanji resume         # open your most recent unfinished match
tuimanji games          # list available games
tuimanji where          # print the resolved database directory
tuimanji --version
```

The shared database defaults to `/var/games/tuimanji/`. On a machine where
you don't own that path, override it:

```bash
export TUIMANJI_DB=~/.local/share/tuimanji
# or per-command
tuimanji --db ~/.local/share/tuimanji
```

Everyone playing against each other has to point at the same directory.

## Games

| id               | players | name              |
| ---------------- | ------- | ----------------- |
| `tic-tac-toe`    | 2       | Tic-Tac-Toe       |
| `connect-4`      | 2       | Connect 4         |
| `battleship`     | 2       | Battleship        |
| `reversi`        | 2       | Reversi           |
| `chess`          | 2       | Chess             |
| `checkers`       | 2       | Checkers          |
| `peg-solitaire`  | 1       | Peg Solitaire     |
| `crazy-eights`   | 2–4     | Crazy Eights      |
| `royal-ur`       | 2       | Royal Game of Ur  |

## Controls

| key             | action                                              |
| --------------- | --------------------------------------------------- |
| `↑ ↓ ← →`       | move cursor                                         |
| `enter` `space` | commit cursor action                                |
| `r`             | rotate ship (Battleship placement phase)            |
| `tab`           | cycle stage / suit / piece (multi-phase games)      |
| `q`             | quit to lobby                                       |

Per-game quirks are surfaced in the status strip at the bottom of each match.

## Adding a game

A game is one module under `src/tuimanji/games/` implementing the
`tuimanji.engine.Game` protocol — pure functions over `state` dicts. No I/O,
no database access. See [`docs/adding-a-game.md`](docs/adding-a-game.md) for
a walkthrough, or read `src/tuimanji/games/peg_solitaire.py` for the minimal
single-player shape.

```python
from tuimanji import Game, REGISTRY, IllegalAction

class MyGame:  # satisfies the Game protocol structurally
    id = "my-game"
    name = "My Game"
    min_players = 2
    max_players = 2
    # ... initial_state, apply_action, current_player, winner, is_terminal,
    # ... render, initial_cursor, move_cursor, cursor_action, animation_for
```

## Development

```bash
git clone https://github.com/alanbato/tuimanji
cd tuimanji
uv sync
uv run pytest -q
prek install    # pre-commit hooks (ruff, ty)
uv run tuimanji
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).

Modifications served over a network must be offered in source form — the
AGPL's network clause applies. Tuimanji doesn't currently run as a network
service, but derivative works that do should keep this in mind.

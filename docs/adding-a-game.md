# Adding a game

This is a walkthrough for adding a new game to tuimanji. It assumes you've
read the top-level [README](../README.md) and [CLAUDE.md](../CLAUDE.md) for
the design constraints.

We'll build **Dots and Boxes** (the pencil-and-paper game where players
alternate drawing single edges on a grid of dots; completing a box scores a
point and grants another turn). The goal is to show the mechanical shape of
a game module, not ship a production version — we'll sketch the core and
leave rendering polish as an exercise.

## The `Game` protocol

Every game implements `tuimanji.engine.Game` structurally — it's a
`Protocol`, so you don't subclass, you just match the shape:

```python
class Game(Protocol):
    id: str                                             # stable slug
    name: str                                           # human-readable
    min_players: int
    max_players: int

    def initial_state(self, players: list[str]) -> dict[str, Any]: ...
    def apply_action(self, state, player, action) -> dict[str, Any]: ...
    def current_player(self, state) -> str | None: ...
    def winner(self, state) -> str | None: ...
    def is_terminal(self, state) -> bool: ...
    def render(self, state, viewport, ui=None) -> list[Strip]: ...

    # Cursor model — lets MatchScreen stay game-agnostic.
    def initial_cursor(self) -> dict[str, Any]: ...
    def move_cursor(self, cursor, dr, dc) -> dict[str, Any]: ...
    def cursor_action(self, cursor) -> dict[str, Any]: ...

    # Optional animation hook (return None when unused).
    def animation_for(self, prev_state, new_state) -> Animation | None: ...
```

The important constraint: **all methods are pure.** No I/O, no clocks, no
random number generators seeded off the wall clock. If your game needs
randomness (like Crazy Eights or Royal Game of Ur), compute it inside
`apply_action` using a seed stored in `state` so the whole thing is
reproducible — see `games/crazy_eights.py` for the pattern.

## 1. Skeleton

Create `src/tuimanji/games/dots_and_boxes.py`:

```python
"""Dots and Boxes — alternate drawing edges on a grid, complete a box to score.

Action schema::

    {"type": "hline", "row": int, "col": int}   # horizontal edge north of (row, col)
    {"type": "vline", "row": int, "col": int}   # vertical edge west of (row, col)
"""

from typing import Any

from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ._common import empty_grid, opponent_of


ROWS = 4
COLS = 4


class DotsAndBoxes:
    id = "dots-and-boxes"
    name = "Dots and Boxes"
    min_players = 2
    max_players = 2
```

## 2. `initial_state`

Pick a state shape that round-trips through JSON — no tuples, no sets, no
custom classes:

```python
    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 2:
            raise ValueError("dots-and-boxes requires exactly 2 players")
        return {
            "hlines": empty_grid(ROWS + 1, COLS, " "),      # horizontals
            "vlines": empty_grid(ROWS, COLS + 1, " "),      # verticals
            "boxes": empty_grid(ROWS, COLS, " "),           # owners
            "scores": {players[0]: 0, players[1]: 0},
            "order": list(players),
            "turn_player": players[0],
            "winner": None,
        }
```

## 3. `apply_action`

This is where the rules live. Treat `state` as frozen — build a copy and
return the new version:

```python
    def apply_action(self, state, player, action):
        if self.is_terminal(state):
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")

        atype = action.get("type")
        if atype not in {"hline", "vline"}:
            raise IllegalAction(f"expected hline/vline, got {atype}")

        # ... rule enforcement, scoring, turn advance ...
```

A tip from every existing game: **validate loudly.** Raise `IllegalAction`
with a message specific enough that a player staring at the UI understands
what went wrong. "cell (3,2) is taken" beats "invalid action".

## 4. Cursor trio

The `MatchScreen` holds an opaque cursor dict and asks the game to mutate
and interpret it. For a grid game:

```python
    def initial_cursor(self):
        return {"row": 0, "col": 0, "axis": "h"}

    def move_cursor(self, cursor, dr, dc):
        return {**cursor,
                "row": (cursor["row"] + dr) % (ROWS + 1),
                "col": (cursor["col"] + dc) % (COLS + 1)}

    def cursor_action(self, cursor):
        return {"type": f"{cursor['axis']}line",
                "row": cursor["row"], "col": cursor["col"]}
```

For a multi-phase game (like Battleship's place-then-fire, or our h/v edge
toggle), tuimanji has optional cursor hooks (`rotate_cursor`, `stage_cursor`,
`sync_cursor`) that `MatchScreen` picks up with `getattr` — just add the
method, don't widen the protocol.

## 5. `render`

Return a list of `textual.strip.Strip` rows. Reach for `games/_common.py`
before copy-pasting from another game — it has `empty_grid`, `grid_top`,
`grid_sep`, `grid_bot`, `col_labels`, `cursor_bracket`, `cursor_palette`,
and theme-aware style helpers.

Read colors from `ui["theme"]` via `tuimanji.ui.theme.style(...)`:

```python
from ..ui.theme import style

def render(self, state, viewport, ui=None):
    ui = ui or {}
    theme = ui.get("theme")
    grid_style = style(theme, "muted")
    ...
```

Don't hardcode `rich.Style(color="blue")` — it kills testability and fights
the user's chosen theme.

## 6. Register

Add to `src/tuimanji/games/__init__.py`:

```python
from .dots_and_boxes import DotsAndBoxes

REGISTRY: dict[str, Game] = {
    # ... existing games ...
    DotsAndBoxes.id: DotsAndBoxes(),
}
```

## 7. Test

Add `tests/test_dots_and_boxes.py`. Because the game is pure, tests are
plain dict manipulations:

```python
from tuimanji.games.dots_and_boxes import DotsAndBoxes
from tuimanji.engine import IllegalAction

def test_initial_state_has_two_players():
    g = DotsAndBoxes()
    s = g.initial_state(["alice", "bob"])
    assert s["turn_player"] == "alice"
    assert s["scores"] == {"alice": 0, "bob": 0}

def test_cannot_draw_same_line_twice():
    g = DotsAndBoxes()
    s = g.initial_state(["alice", "bob"])
    s = g.apply_action(s, "alice", {"type": "hline", "row": 0, "col": 0})
    import pytest
    with pytest.raises(IllegalAction):
        g.apply_action(s, "bob", {"type": "hline", "row": 0, "col": 0})
```

At minimum, cover:

- Initial state shape
- Rule violations raise `IllegalAction`
- Turn ordering
- A full win path to verify `is_terminal` / `winner`

## 8. Run it

```bash
uv run tuimanji games                # should list "dots-and-boxes"
uv run tuimanji new dots-and-boxes
```

Open a second terminal (or log in as a different user) to join the waiting
room, and you're playing.

## Where to look next

- **`peg_solitaire.py`** — minimal single-player template
- **`tic_tac_toe.py`** — minimal 2-player grid game
- **`connect4.py`** — first game with animations (`animation_for`)
- **`battleship.py`** — phased games, hidden-information rendering
- **`crazy_eights.py`** — reproducible randomness baked into state
- **`royal_ur.py`** — multi-action turns (roll, then move) with phase dispatch

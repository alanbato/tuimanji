"""Battleship — 10×10 grids, hidden ship placement, alternate firing.

Two phases keyed off ``state["phase"]``:

- ``"place"`` — each player submits ``{"type": "place", "ships": [...]}``
  with ship positions; phase advances to ``"fire"`` once both have placed.
- ``"fire"`` — players alternate ``{"type": "fire", "row": r, "col": c}``
  until one side has all ships sunk.

Hidden information is handled at render time via ``ui["viewer"]`` — the
engine keeps full state, and ``render`` masks the opponent's ships for
the viewer.
"""

from dataclasses import dataclass
from typing import Any, ClassVar

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import style
from ._common import (
    EMPTY,
    cell_segments,
    col_labels,
    copy_grid,
    cursor_bracket,
    cursor_palette,
    empty_grid,
    grid_bot,
    grid_sep,
    grid_top,
    header_palette,
    in_bounds,
    opponent_of,
    wrap_cursor,
)

SIZE = 10
HIT = "H"
MISS = "M"


@dataclass
class ExplodeAnimation:
    row: int
    col: int
    interval: float = 0.12
    frames: int = 4
    _GLYPHS: ClassVar[list[str]] = ["O", "o", "✸", "X"]

    def overlay(self, frame: int) -> dict[str, Any]:
        f = max(0, min(frame, self.frames - 1))
        return {
            "kind": "explode",
            "row": self.row,
            "col": self.col,
            "glyph": self._GLYPHS[f],
        }


# (name, length, board-mark)
FLEET: list[tuple[str, int, str]] = [
    ("Carrier", 5, "C"),
    ("Battleship", 4, "B"),
    ("Cruiser", 3, "R"),
    ("Submarine", 3, "S"),
    ("Destroyer", 2, "D"),
]
FLEET_NAMES = [name for name, _, _ in FLEET]
FLEET_LEN = {name: length for name, length, _ in FLEET}
FLEET_MARK = {name: mark for name, _, mark in FLEET}


def _ship_cells(row: int, col: int, length: int, direction: str) -> list[list[int]]:
    if direction == "h":
        return [[row, col + i] for i in range(length)]
    if direction == "v":
        return [[row + i, col] for i in range(length)]
    raise IllegalAction(f"bad direction: {direction}")


def _cells_in_bounds(cells: list[list[int]]) -> bool:
    return all(in_bounds(r, c, SIZE, SIZE) for r, c in cells)


class Battleship:
    id = "battleship"
    name = "Battleship"
    min_players = 2
    max_players = 2

    # ---------- lifecycle ----------

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 2:
            raise ValueError("battleship requires exactly 2 players")
        p1, p2 = players
        return {
            "phase": "placement",
            "order": [p1, p2],
            "turn_player": p1,  # whoever submits first; both write once during placement
            "boards": {p1: empty_grid(SIZE, SIZE), p2: empty_grid(SIZE, SIZE)},
            "shots": {p1: empty_grid(SIZE, SIZE), p2: empty_grid(SIZE, SIZE)},
            "fleets": {p1: [], p2: []},
            "placed": {p1: False, p2: False},
            "last_shot": None,
            "winner": None,
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if state.get("winner") is not None:
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")
        atype = action.get("type")
        if state["phase"] == "placement":
            if atype != "place_fleet":
                raise IllegalAction(f"expected place_fleet, got {atype}")
            return self._apply_placement(state, player, action)
        if state["phase"] == "battle":
            if atype != "fire":
                raise IllegalAction(f"expected fire, got {atype}")
            return self._apply_fire(state, player, action)
        raise IllegalAction(f"unknown phase: {state['phase']}")

    # ---------- placement ----------

    def _apply_placement(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if state["placed"][player]:
            raise IllegalAction(f"{player} already placed their fleet")
        ships_in = action.get("ships")
        if not isinstance(ships_in, list) or len(ships_in) != len(FLEET):
            raise IllegalAction(f"need exactly {len(FLEET)} ships")
        names_seen: set[str] = set()
        board = empty_grid(SIZE, SIZE)
        fleet: list[dict[str, Any]] = []
        for entry in ships_in:
            try:
                name = str(entry["name"])
                row = int(entry["row"])
                col = int(entry["col"])
                direction = str(entry["dir"])
            except (KeyError, TypeError, ValueError) as e:
                raise IllegalAction(f"bad ship entry: {entry}") from e
            if name not in FLEET_LEN:
                raise IllegalAction(f"unknown ship: {name}")
            if name in names_seen:
                raise IllegalAction(f"duplicate ship: {name}")
            names_seen.add(name)
            length = FLEET_LEN[name]
            cells = _ship_cells(row, col, length, direction)
            if not _cells_in_bounds(cells):
                raise IllegalAction(f"{name} out of bounds")
            for r, c in cells:
                if board[r][c] != EMPTY:
                    raise IllegalAction(f"{name} overlaps another ship")
                board[r][c] = FLEET_MARK[name]
            fleet.append(
                {
                    "name": name,
                    "len": length,
                    "cells": cells,
                    "sunk": False,
                }
            )
        if names_seen != set(FLEET_NAMES):
            missing = sorted(set(FLEET_NAMES) - names_seen)
            raise IllegalAction(f"missing ships: {missing}")

        new_boards = {**state["boards"], player: board}
        new_fleets = {**state["fleets"], player: fleet}
        new_placed = {**state["placed"], player: True}
        opponent = opponent_of(state["order"], player)
        if new_placed[opponent]:
            phase = "battle"
            turn_player = state["order"][0]
        else:
            phase = "placement"
            turn_player = opponent
        return {
            **state,
            "boards": new_boards,
            "fleets": new_fleets,
            "placed": new_placed,
            "phase": phase,
            "turn_player": turn_player,
            "last_shot": None,
        }

    # ---------- battle ----------

    def _apply_fire(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            row = int(action["row"])
            col = int(action["col"])
        except (KeyError, TypeError, ValueError) as e:
            raise IllegalAction(f"bad fire action: {action}") from e
        if not (0 <= row < SIZE and 0 <= col < SIZE):
            raise IllegalAction(f"out of bounds: ({row},{col})")
        opponent = opponent_of(state["order"], player)
        opp_shots_old = state["shots"][opponent]
        if opp_shots_old[row][col] != EMPTY:
            raise IllegalAction(f"already shot at ({row},{col})")
        opp_board = state["boards"][opponent]
        is_hit = opp_board[row][col] != EMPTY

        new_opp_shots = copy_grid(opp_shots_old)
        new_opp_shots[row][col] = HIT if is_hit else MISS
        new_shots = {**state["shots"], opponent: new_opp_shots}

        new_opp_fleet = [dict(s) for s in state["fleets"][opponent]]
        sunk_name: str | None = None
        if is_hit:
            for ship in new_opp_fleet:
                if [row, col] in ship["cells"]:
                    if all(new_opp_shots[r][c] == HIT for r, c in ship["cells"]):
                        ship["sunk"] = True
                        sunk_name = ship["name"]
                    break
        new_fleets = {**state["fleets"], opponent: new_opp_fleet}

        all_sunk = all(s["sunk"] for s in new_opp_fleet)
        winner = player if all_sunk else None
        phase = "finished" if all_sunk else "battle"
        next_player = player if all_sunk else opponent

        return {
            **state,
            "shots": new_shots,
            "fleets": new_fleets,
            "turn_player": next_player,
            "phase": phase,
            "winner": winner,
            "last_shot": {
                "player": player,
                "row": row,
                "col": col,
                "hit": is_hit,
                "sunk": sunk_name,
            },
        }

    # ---------- protocol queries ----------

    def current_player(self, state: dict[str, Any]) -> str | None:
        if self.is_terminal(state):
            return None
        return state["turn_player"]

    def winner(self, state: dict[str, Any]) -> str | None:
        return state.get("winner")

    def is_terminal(self, state: dict[str, Any]) -> bool:
        return state.get("winner") is not None

    # ---------- cursor ----------

    def initial_cursor(self) -> dict[str, Any]:
        return {
            "mode": "placement",
            "row": 0,
            "col": 0,
            "ship_idx": 0,
            "dir": "h",
            "placed": [],
        }

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        return wrap_cursor(cursor, dr, dc, SIZE, SIZE)

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        if cursor["mode"] == "placement":
            if cursor["ship_idx"] < len(FLEET):
                raise IllegalAction("place all ships before submitting (press space)")
            return {"type": "place_fleet", "ships": list(cursor["placed"])}
        return {"type": "fire", "row": cursor["row"], "col": cursor["col"]}

    # Optional helpers — MatchScreen calls these via getattr.
    def rotate_cursor(self, cursor: dict[str, Any]) -> dict[str, Any]:
        if cursor["mode"] != "placement" or cursor["ship_idx"] >= len(FLEET):
            return cursor
        return {**cursor, "dir": "v" if cursor["dir"] == "h" else "h"}

    def stage_cursor(self, cursor: dict[str, Any]) -> dict[str, Any]:
        if cursor["mode"] != "placement" or cursor["ship_idx"] >= len(FLEET):
            return cursor
        idx = cursor["ship_idx"]
        name, length, _ = FLEET[idx]
        cells = _ship_cells(cursor["row"], cursor["col"], length, cursor["dir"])
        if not _cells_in_bounds(cells):
            raise IllegalAction(f"{name} out of bounds")
        occupied: set[tuple[int, int]] = set()
        for prior in cursor["placed"]:
            for r, c in _ship_cells(
                prior["row"], prior["col"], FLEET_LEN[prior["name"]], prior["dir"]
            ):
                occupied.add((r, c))
        for r, c in cells:
            if (r, c) in occupied:
                raise IllegalAction(f"{name} overlaps another ship")
        new_placed = list(cursor["placed"]) + [
            {
                "name": name,
                "row": cursor["row"],
                "col": cursor["col"],
                "dir": cursor["dir"],
            }
        ]
        return {
            **cursor,
            "placed": new_placed,
            "ship_idx": idx + 1,
        }

    def sync_cursor(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        phase = state.get("phase")
        if phase == "battle" and cursor["mode"] != "battle":
            return {"mode": "battle", "row": 0, "col": 0}
        return cursor

    # ---------- animation ----------

    def animation_for(
        self, prev_state: dict[str, Any], new_state: dict[str, Any]
    ) -> ExplodeAnimation | None:
        shot = new_state.get("last_shot")
        if shot is None or not shot.get("hit"):
            return None
        return ExplodeAnimation(row=int(shot["row"]), col=int(shot["col"]))

    # ---------- render ----------

    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]:
        ui = ui or {}
        cursor = ui.get("cursor") or {}
        active = ui.get("active", True)
        me = ui.get("player")
        anim = ui.get("animation")
        explosion = anim if anim and anim.get("kind") == "explode" else None
        theme = ui.get("theme")

        order = state.get("order", [])
        if me not in order:
            # Spectator / fallback: just show p1's view.
            me = order[0] if order else None
        opponent = opponent_of(order, me) if me in order else None

        phase = state.get("phase", "placement")

        water_style = style(theme, "muted")
        ship_style = style(theme, "primary", bold=True)
        hit_style = style(theme, "error", bold=True)
        miss_style = style(theme, "muted")
        grid_style = style(theme, "primary")
        cursor_active, cursor_inactive = cursor_palette(theme)
        preview_style = style(theme, "success", bold=True)
        staged_style = style(theme, "accent")
        header_style = header_palette(theme)
        sunk_style = style(theme, "error", bold=True, strike=True)

        # Pre-compute the in-progress ship preview cells (placement only).
        preview_cells: set[tuple[int, int]] = set()
        if (
            phase == "placement"
            and cursor.get("mode") == "placement"
            and cursor.get("ship_idx", len(FLEET)) < len(FLEET)
        ):
            idx = cursor["ship_idx"]
            _, length, _ = FLEET[idx]
            try:
                cells = _ship_cells(cursor["row"], cursor["col"], length, cursor["dir"])
                if _cells_in_bounds(cells):
                    preview_cells = {(r, c) for r, c in cells}
            except IllegalAction:
                pass
        staged_cells: set[tuple[int, int]] = set()
        if phase == "placement" and cursor.get("mode") == "placement":
            for prior in cursor.get("placed", []):
                for r, c in _ship_cells(
                    prior["row"],
                    prior["col"],
                    FLEET_LEN[prior["name"]],
                    prior["dir"],
                ):
                    staged_cells.add((r, c))

        def render_target_row(r: int) -> Strip:
            """Top grid: shots I have fired at the opponent."""
            segs: list[Segment] = [Segment("│", grid_style)]
            shots = state["shots"][opponent] if opponent else empty_grid(SIZE, SIZE)
            for c in range(SIZE):
                cell = shots[r][c]
                is_cursor = (
                    phase == "battle"
                    and cursor.get("mode") == "battle"
                    and cursor.get("row") == r
                    and cursor.get("col") == c
                )
                if is_cursor:
                    bg = cursor_active if active else cursor_inactive
                    glyph = "X" if cell == HIT else "~" if cell == MISS else "·"
                    segs.extend(cursor_bracket(glyph, bg))
                elif cell == HIT:
                    segs.extend(cell_segments("X", hit_style))
                elif cell == MISS:
                    segs.extend(cell_segments("~", miss_style))
                else:
                    segs.extend(cell_segments("·", water_style))
                segs.append(Segment("│", grid_style))
            return Strip(segs)

        def render_fleet_row(r: int) -> Strip:
            """Bottom grid: my own board with incoming shots / explosion."""
            segs: list[Segment] = [Segment("│", grid_style)]
            board = state["boards"][me] if me else empty_grid(SIZE, SIZE)
            shots_at_me = state["shots"][me] if me else empty_grid(SIZE, SIZE)
            for c in range(SIZE):
                ship = board[r][c]
                shot = shots_at_me[r][c]
                is_explosion = (
                    isinstance(explosion, dict)
                    and explosion.get("row") == r
                    and explosion.get("col") == c
                )
                is_cursor = (
                    phase == "placement"
                    and cursor.get("mode") == "placement"
                    and cursor.get("row") == r
                    and cursor.get("col") == c
                )
                in_preview = (r, c) in preview_cells
                in_staged = (r, c) in staged_cells

                if is_explosion and isinstance(explosion, dict):
                    segs.extend(cell_segments(str(explosion["glyph"]), hit_style))
                elif phase == "placement" and is_cursor:
                    bg = cursor_active if active else cursor_inactive
                    segs.extend(cursor_bracket("#" if in_preview else "·", bg))
                elif in_preview:
                    segs.extend(cell_segments("#", preview_style))
                elif in_staged:
                    segs.extend(cell_segments("■", staged_style))
                elif shot == HIT:
                    segs.extend(cell_segments("X", hit_style))
                elif shot == MISS:
                    segs.extend(cell_segments("~", miss_style))
                elif ship != EMPTY:
                    segs.extend(cell_segments("■", ship_style))
                else:
                    segs.extend(cell_segments("·", water_style))
                segs.append(Segment("│", grid_style))
            return Strip(segs)

        def grid_block(label: str, row_renderer) -> list[Strip]:
            lines: list[Strip] = [
                Strip([Segment(label, header_style)]),
                col_labels(SIZE, header_style),
                grid_top(SIZE, grid_style),
            ]
            for r in range(SIZE):
                lines.append(row_renderer(r))
                if r < SIZE - 1:
                    lines.append(grid_sep(SIZE, grid_style))
            lines.append(grid_bot(SIZE, grid_style))
            return lines

        # Header & status
        header_text = "  "
        for p in order:
            tag = "✓" if state["placed"].get(p) else "…"
            header_text += f"{p}{tag}  "
        header = Strip([Segment(header_text, header_style)])

        if state.get("winner") is not None:
            status = f"  winner: {state['winner']}"
        elif phase == "placement":
            if cursor.get("mode") == "placement" and me == state.get("turn_player"):
                idx = cursor.get("ship_idx", len(FLEET))
                if idx < len(FLEET):
                    name, length, _ = FLEET[idx]
                    status = (
                        f"  place {name} (len {length}, dir {cursor['dir']})"
                        f" — arrows move, r rotate, space stage, enter submit"
                    )
                else:
                    status = "  fleet ready — press enter to submit"
            else:
                status = f"  waiting for {state.get('turn_player')} to place fleet"
        else:
            shot = state.get("last_shot")
            if shot is not None:
                tag = "HIT" if shot["hit"] else "miss"
                msg = f"{shot['player']} → ({shot['row']},{shot['col']}): {tag}"
                if shot.get("sunk"):
                    msg += f" — sunk {shot['sunk']}!"
                status = "  " + msg
            else:
                status = f"  turn: {state.get('turn_player')}"

        # Fleet status line: which of my opponent's ships I've sunk.
        sunk_line_segs: list[Segment] = [Segment("  enemy: ", header_style)]
        if opponent and state["fleets"][opponent]:
            for ship in state["fleets"][opponent]:
                ship_label_style = sunk_style if ship["sunk"] else header_style
                sunk_line_segs.append(Segment(f"{ship['name'][0]} ", ship_label_style))
        sunk_line = Strip(sunk_line_segs)

        lines: list[Strip] = [header]
        lines.extend(grid_block("  TARGET (your shots)", render_target_row))
        lines.append(Strip([Segment("")]))
        lines.extend(grid_block("  FLEET (your ships)", render_fleet_row))
        lines.append(Strip([Segment("")]))
        lines.append(sunk_line)
        lines.append(Strip([Segment(status, Style(italic=True))]))
        return lines

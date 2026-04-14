from dataclasses import dataclass, field
from typing import Any, ClassVar

from rich.segment import Segment
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import style
from ._common import (
    EMPTY,
    copy_grid,
    cursor_palette,
    empty_grid,
    grid_bot,
    grid_sep,
    grid_top,
    header_palette,
    in_bounds,
    opponent_of,
    order_header,
    status_strip,
    wrap_cursor,
)

ROWS = 8
COLS = 8
DIRS = [
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
]


@dataclass
class FlipAnimation:
    cells: list[list[int]] = field(default_factory=list)
    at: list[int] = field(default_factory=list)
    to: str = ""
    interval: float = 0.08
    frames: int = 4
    _GLYPHS: ClassVar[list[str]] = ["◐", "◓", "◑", "◒"]

    def overlay(self, frame: int) -> dict[str, Any]:
        return {
            "kind": "flip",
            "cells": self.cells,
            "at": self.at,
            "to": self.to,
            "glyph": self._GLYPHS[frame % self.frames],
        }


def _captures(
    board: list[list[str]], r: int, c: int, mark: str
) -> list[tuple[int, int]]:
    opp = "W" if mark == "B" else "B"
    flipped: list[tuple[int, int]] = []
    for dr, dc in DIRS:
        run: list[tuple[int, int]] = []
        rr, cc = r + dr, c + dc
        while in_bounds(rr, cc, ROWS, COLS) and board[rr][cc] == opp:
            run.append((rr, cc))
            rr += dr
            cc += dc
        if run and in_bounds(rr, cc, ROWS, COLS) and board[rr][cc] == mark:
            flipped.extend(run)
    return flipped


def _legal_moves(
    board: list[list[str]], mark: str
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    moves: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for r in range(ROWS):
        for c in range(COLS):
            if board[r][c] != EMPTY:
                continue
            flips = _captures(board, r, c, mark)
            if flips:
                moves[(r, c)] = flips
    return moves


class Reversi:
    id = "reversi"
    name = "Reversi"
    min_players = 2
    max_players = 2

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 2:
            raise ValueError("reversi requires exactly 2 players")
        board = empty_grid(ROWS, COLS)
        board[3][3] = "W"
        board[4][4] = "W"
        board[3][4] = "B"
        board[4][3] = "B"
        return {
            "board": board,
            "marks": {players[0]: "B", players[1]: "W"},
            "order": list(players),
            "turn_player": players[0],
            "winner": None,
            "last_flip": None,
            "last_pass": None,
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if self.is_terminal(state):
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")
        try:
            r, c = int(action["row"]), int(action["col"])
        except (KeyError, TypeError, ValueError) as e:
            raise IllegalAction(f"bad action: {action}") from e
        if not in_bounds(r, c, ROWS, COLS):
            raise IllegalAction(f"out of bounds: ({r},{c})")
        board = copy_grid(state["board"])
        if board[r][c] != EMPTY:
            raise IllegalAction(f"cell ({r},{c}) is taken")
        mark = state["marks"][player]
        flips = _captures(board, r, c, mark)
        if not flips:
            raise IllegalAction(f"no captures at ({r},{c})")
        board[r][c] = mark
        for fr, fc in flips:
            board[fr][fc] = mark

        order = state["order"]
        opp = opponent_of(order, player)
        opp_mark = state["marks"][opp]
        passed: str | None = None
        if _legal_moves(board, opp_mark):
            next_player = opp
        elif _legal_moves(board, mark):
            next_player = player
            passed = opp
        else:
            next_player = opp

        new_state = {
            **state,
            "board": board,
            "turn_player": next_player,
            "last_flip": {
                "at": [r, c],
                "cells": [[fr, fc] for fr, fc in flips],
                "to": mark,
            },
            "last_pass": passed,
        }
        if self.is_terminal(new_state):
            new_state["winner"] = self._winner_by_count(board, state["marks"])
        return new_state

    def _winner_by_count(
        self, board: list[list[str]], marks: dict[str, str]
    ) -> str | None:
        counts: dict[str, int] = {m: 0 for m in marks.values()}
        for row in board:
            for cell in row:
                if cell in counts:
                    counts[cell] += 1
        inv = {v: k for k, v in marks.items()}
        pairs = list(counts.items())
        (m_a, n_a), (m_b, n_b) = pairs[0], pairs[1]
        if n_a > n_b:
            return inv[m_a]
        if n_b > n_a:
            return inv[m_b]
        return None

    def current_player(self, state: dict[str, Any]) -> str | None:
        if self.is_terminal(state):
            return None
        return state["turn_player"]

    def winner(self, state: dict[str, Any]) -> str | None:
        return state.get("winner")

    def is_terminal(self, state: dict[str, Any]) -> bool:
        board = state["board"]
        marks = state["marks"]
        order = state["order"]
        if all(cell != EMPTY for row in board for cell in row):
            return True
        for p in order:
            if _legal_moves(board, marks[p]):
                return False
        return True

    def initial_cursor(self) -> dict[str, Any]:
        return {"row": 3, "col": 3}

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        return wrap_cursor(cursor, dr, dc, ROWS, COLS)

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        return {"row": cursor["row"], "col": cursor["col"]}

    def animation_for(
        self, prev_state: dict[str, Any], new_state: dict[str, Any]
    ) -> FlipAnimation | None:
        flip = new_state.get("last_flip")
        if flip is None:
            return None
        cells = flip.get("cells") or []
        if not cells:
            return None
        return FlipAnimation(
            cells=[list(c) for c in cells],
            at=list(flip["at"]),
            to=flip["to"],
        )

    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]:
        ui = ui or {}
        cur = ui.get("cursor")
        cursor = (cur["row"], cur["col"]) if cur is not None else None
        active = ui.get("active", True)
        theme = ui.get("theme")
        anim = ui.get("animation")
        flipping = anim if anim and anim.get("kind") == "flip" else None
        me = ui.get("player")

        board = state["board"]
        grid_style = style(theme, "primary")
        empty_style = style(theme, "muted")
        hint_style = style(theme, "success", bold=True)
        flip_style = style(theme, "warning", bold=True)
        cursor_active, cursor_inactive = cursor_palette(theme)
        glyph_styles = {
            "B": style(theme, "primary", bold=True),
            "W": style(theme, "accent", bold=True),
        }

        hints: set[tuple[int, int]] = set()
        turn_mark = state["marks"].get(state.get("turn_player"))
        if (
            me is not None
            and state.get("turn_player") == me
            and turn_mark is not None
            and not self.is_terminal(state)
        ):
            hints = set(_legal_moves(board, turn_mark).keys())

        flip_cells: set[tuple[int, int]] = set()
        flip_glyph: str = ""
        flip_at: tuple[int, int] | None = None
        flip_to: str | None = None
        if flipping is not None:
            flip_cells = {(int(r), int(c)) for r, c in flipping.get("cells", [])}
            flip_glyph = str(flipping.get("glyph", ""))
            at = flipping.get("at")
            if at:
                flip_at = (int(at[0]), int(at[1]))
            flip_to = flipping.get("to")

        def cell_segs(r: int, c: int) -> list[Segment]:
            ch = board[r][c]
            if flip_at == (r, c) and flip_to in ("B", "W"):
                glyph = "●" if flip_to == "B" else "○"
                st = glyph_styles[flip_to]
            elif (r, c) in flip_cells:
                glyph = flip_glyph
                st = flip_style
            elif ch == "B":
                glyph, st = "●", glyph_styles["B"]
            elif ch == "W":
                glyph, st = "○", glyph_styles["W"]
            elif (r, c) in hints:
                glyph, st = "∘", hint_style
            else:
                glyph, st = "·", empty_style
            if cursor == (r, c):
                bg = cursor_active if active else cursor_inactive
                return [Segment("[", bg), Segment(glyph, bg), Segment("]", bg)]
            return [Segment(" "), Segment(glyph, st), Segment(" ")]

        def row_strip(r: int) -> Strip:
            segs: list[Segment] = [Segment("│", grid_style)]
            for c in range(COLS):
                segs.extend(cell_segs(r, c))
                segs.append(Segment("│", grid_style))
            return Strip(segs)

        header_style = header_palette(theme)
        glyph_marks = {p: "●" if m == "B" else "○" for p, m in state["marks"].items()}
        header_state = {**state, "marks": glyph_marks}
        lines: list[Strip] = [
            order_header(header_state, header_style),
            grid_top(COLS, grid_style),
        ]
        for r in range(ROWS):
            lines.append(row_strip(r))
            if r < ROWS - 1:
                lines.append(grid_sep(COLS, grid_style))
        lines.append(grid_bot(COLS, grid_style))

        b_count = sum(1 for row in board for cell in row if cell == "B")
        w_count = sum(1 for row in board for cell in row if cell == "W")
        lines.append(Strip([Segment("")]))
        lines.append(Strip([Segment(f"  ● {b_count}   ○ {w_count}", header_style)]))

        if self.is_terminal(state):
            w = state.get("winner")
            status = f"  winner: {w}" if w else "  draw"
        else:
            status = f"  turn: {state.get('turn_player')}"
            if state.get("last_pass"):
                status += f"  ({state['last_pass']} had no moves and passed)"
        lines.append(status_strip(status))
        return lines

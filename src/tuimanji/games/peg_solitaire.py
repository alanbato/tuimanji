from typing import Any

from rich.segment import Segment
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import style
from ._common import (
    EMPTY,
    copy_grid,
    cursor_bracket,
    cursor_palette,
    header_palette,
    status_strip,
)

SIZE = 7
PEG = "O"
VOID = "#"

_DIRS = [(-2, 0), (2, 0), (0, -2), (0, 2)]


def _is_void(r: int, c: int) -> bool:
    return (r < 2 or r >= 5) and (c < 2 or c >= 5)


def _empty_cross() -> list[list[str]]:
    grid: list[list[str]] = []
    for r in range(SIZE):
        row: list[str] = []
        for c in range(SIZE):
            if _is_void(r, c):
                row.append(VOID)
            elif r == 3 and c == 3:
                row.append(EMPTY)
            else:
                row.append(PEG)
        grid.append(row)
    return grid


def _has_moves(board: list[list[str]]) -> bool:
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] != PEG:
                continue
            for dr, dc in _DIRS:
                tr, tc = r + dr, c + dc
                if not (0 <= tr < SIZE and 0 <= tc < SIZE):
                    continue
                if board[tr][tc] != EMPTY:
                    continue
                mr, mc = r + dr // 2, c + dc // 2
                if board[mr][mc] == PEG:
                    return True
    return False


def _peg_count(board: list[list[str]]) -> int:
    return sum(1 for row in board for cell in row if cell == PEG)


class PegSolitaire:
    id = "peg-solitaire"
    name = "Peg Solitaire"
    min_players = 1
    max_players = 1

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 1:
            raise ValueError("peg solitaire requires exactly 1 player")
        return {
            "board": _empty_cross(),
            "order": list(players),
            "turn_player": players[0],
            "winner": None,
            "moves": 0,
            "last_move": None,
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if self.is_terminal(state):
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")
        try:
            frm = action["from"]
            to = action["to"]
            fr, fc = int(frm[0]), int(frm[1])
            tr, tc = int(to[0]), int(to[1])
        except (KeyError, TypeError, IndexError, ValueError) as e:
            raise IllegalAction(f"bad action: {action}") from e
        for r, c in ((fr, fc), (tr, tc)):
            if not (0 <= r < SIZE and 0 <= c < SIZE) or _is_void(r, c):
                raise IllegalAction(f"out of bounds: ({r},{c})")
        board = state["board"]
        if board[fr][fc] != PEG:
            raise IllegalAction("source must be a peg")
        if board[tr][tc] != EMPTY:
            raise IllegalAction("destination must be empty")
        dr, dc = tr - fr, tc - fc
        if not ((abs(dr) == 2 and dc == 0) or (abs(dc) == 2 and dr == 0)):
            raise IllegalAction("jumps must be two squares horizontally or vertically")
        mr, mc = fr + dr // 2, fc + dc // 2
        if board[mr][mc] != PEG:
            raise IllegalAction("must jump over a peg")
        new_board = copy_grid(board)
        new_board[fr][fc] = EMPTY
        new_board[mr][mc] = EMPTY
        new_board[tr][tc] = PEG
        remaining = _peg_count(new_board)
        stuck = not _has_moves(new_board)
        winner = player if stuck and remaining == 1 else None
        return {
            **state,
            "board": new_board,
            "moves": state["moves"] + 1,
            "last_move": {"from": [fr, fc], "over": [mr, mc], "to": [tr, tc]},
            "winner": winner,
        }

    def current_player(self, state: dict[str, Any]) -> str | None:
        if self.is_terminal(state):
            return None
        return state["turn_player"]

    def winner(self, state: dict[str, Any]) -> str | None:
        return state.get("winner")

    def is_terminal(self, state: dict[str, Any]) -> bool:
        if state.get("winner") is not None:
            return True
        return not _has_moves(state["board"])

    def initial_cursor(self) -> dict[str, Any]:
        return {"row": 5, "col": 3, "mode": "select", "from": None}

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        return {
            **cursor,
            "row": (cursor["row"] + dr) % SIZE,
            "col": (cursor["col"] + dc) % SIZE,
        }

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        if cursor["mode"] != "target":
            raise IllegalAction("select a peg first")
        frm = cursor.get("from")
        if frm is None:
            raise IllegalAction("no peg selected")
        return {
            "from": [int(frm[0]), int(frm[1])],
            "to": [cursor["row"], cursor["col"]],
        }

    def prepare_action(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any] | None:
        if cursor["mode"] != "select":
            return None
        r, c = cursor["row"], cursor["col"]
        if _is_void(r, c):
            raise IllegalAction("not a peg")
        if state["board"][r][c] != PEG:
            raise IllegalAction("not a peg")
        return {**cursor, "mode": "target", "from": [r, c]}

    def stage_cursor(self, cursor: dict[str, Any]) -> dict[str, Any]:
        if cursor["mode"] != "target":
            return cursor
        frm = cursor.get("from")
        row, col = (
            (int(frm[0]), int(frm[1]))
            if frm is not None
            else (cursor["row"], cursor["col"])
        )
        return {**cursor, "mode": "select", "from": None, "row": row, "col": col}

    def sync_cursor(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        if cursor["mode"] != "target":
            return cursor
        frm = cursor.get("from")
        if frm is None:
            return cursor
        fr, fc = int(frm[0]), int(frm[1])
        if state["board"][fr][fc] != PEG:
            return {**cursor, "mode": "select", "from": None}
        return cursor

    def animation_for(
        self, prev_state: dict[str, Any], new_state: dict[str, Any]
    ) -> None:
        return None

    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]:
        board = state["board"]
        ui = ui or {}
        cur = ui.get("cursor") or {}
        active = ui.get("active", True)
        theme = ui.get("theme")
        cursor_pos = (cur.get("row"), cur.get("col"))
        sel = cur.get("from")
        selected = (int(sel[0]), int(sel[1])) if sel else None

        peg_style = style(theme, "primary", bold=True)
        empty_style = style(theme, "muted")
        sel_style = style(theme, "success", bold=True)
        cursor_active, cursor_inactive = cursor_palette(theme)
        header_style = header_palette(theme)

        def cell_segs(r: int, c: int) -> list[Segment]:
            ch = board[r][c]
            if ch == VOID:
                return [Segment("   ")]
            glyph = "●" if ch == PEG else "○"
            if (r, c) == cursor_pos:
                bg = cursor_active if active else cursor_inactive
                return cursor_bracket(glyph, bg)
            if selected is not None and (r, c) == selected:
                return [Segment(" "), Segment(glyph, sel_style), Segment(" ")]
            gs = peg_style if ch == PEG else empty_style
            return [Segment(" "), Segment(glyph, gs), Segment(" ")]

        pegs = _peg_count(board)
        player = state["order"][0] if state.get("order") else ""
        header = f"  {player}  moves: {state['moves']}  pegs: {pegs}"
        blank = Strip([Segment("")])

        lines: list[Strip] = [Strip([Segment(header, header_style)]), blank]
        for r in range(SIZE):
            segs: list[Segment] = [Segment(" ")]
            for c in range(SIZE):
                segs.extend(cell_segs(r, c))
            lines.append(Strip(segs))
        lines.append(blank)

        if state.get("winner") is not None:
            center = board[3][3] == PEG
            tag = "perfect!" if center else "solved!"
            status = f"  {tag}  ({state['moves']} moves)"
        elif self.is_terminal(state):
            status = f"  stuck with {pegs} pegs — no moves left"
        elif cur.get("mode") == "target":
            status = "  choose destination — enter to jump, space cancels"
        else:
            status = "  choose a peg — enter to select"
        lines.append(status_strip(status))
        return lines

"""English draughts — forced captures, multi-jump continuation, promotion ends turn.

Multi-jumps are expressed as a sequence of single-jump actions. After a capture
that doesn't promote, `apply_action` sets `continue_from` and keeps `turn_player`
the same, so the next submitted action must start from that square — the DB
sees each jump as its own turn row, preserving the append-only invariant.
"""

from typing import Any

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import contrast_on_hex, contrast_style, shifted_color, style
from ._common import (
    copy_grid,
    cursor_bracket,
    cursor_palette,
    empty_grid,
    in_bounds,
    opponent_of,
    status_strip,
    wrap_cursor,
)

SIZE = 8
EMPTY_CELL = ""

RED = "r"
WHITE = "w"
RED_KING = "R"
WHITE_KING = "W"

RED_DIRS: list[tuple[int, int]] = [(-1, -1), (-1, 1)]
WHITE_DIRS: list[tuple[int, int]] = [(1, -1), (1, 1)]
KING_DIRS: list[tuple[int, int]] = [(-1, -1), (-1, 1), (1, -1), (1, 1)]

# Arrow keys are cardinal, but checkers only lives on dark diagonals. Rotate
# each arrow 45° clockwise so up=NE, right=SE, down=SW, left=NW, giving the
# player one-press access to every adjacent dark square.
_ARROW_TO_DIAG: dict[tuple[int, int], tuple[int, int]] = {
    (-1, 0): (-1, 1),
    (1, 0): (1, -1),
    (0, -1): (-1, -1),
    (0, 1): (1, 1),
}

GLYPHS: dict[str, str] = {
    RED: "●",
    WHITE: "●",
    RED_KING: "◉",
    WHITE_KING: "◉",
}


def piece_color(p: str) -> str:
    if not p:
        return ""
    return RED if p in (RED, RED_KING) else WHITE


def is_king(p: str) -> bool:
    return p in (RED_KING, WHITE_KING)


def piece_dirs(p: str) -> list[tuple[int, int]]:
    if is_king(p):
        return KING_DIRS
    return RED_DIRS if p == RED else WHITE_DIRS


def _is_dark(r: int, c: int) -> bool:
    return (r + c) % 2 == 1


def _initial_board() -> list[list[str]]:
    b = empty_grid(SIZE, SIZE, fill=EMPTY_CELL)
    for r in range(3):
        for c in range(SIZE):
            if _is_dark(r, c):
                b[r][c] = WHITE
    for r in range(5, SIZE):
        for c in range(SIZE):
            if _is_dark(r, c):
                b[r][c] = RED
    return b


def _king_row_for(color: str) -> int:
    return 0 if color == RED else SIZE - 1


def _piece_jumps(
    board: list[list[str]], r: int, c: int
) -> list[tuple[int, int, int, int]]:
    """Single-step jumps from (r,c): (land_r, land_c, captured_r, captured_c)."""
    piece = board[r][c]
    if not piece:
        return []
    color = piece_color(piece)
    out: list[tuple[int, int, int, int]] = []
    for dr, dc in piece_dirs(piece):
        mid_r, mid_c = r + dr, c + dc
        land_r, land_c = r + 2 * dr, c + 2 * dc
        if not in_bounds(land_r, land_c, SIZE, SIZE):
            continue
        mid = board[mid_r][mid_c]
        if not mid or piece_color(mid) == color:
            continue
        if board[land_r][land_c]:
            continue
        out.append((land_r, land_c, mid_r, mid_c))
    return out


def _piece_steps(board: list[list[str]], r: int, c: int) -> list[tuple[int, int]]:
    piece = board[r][c]
    if not piece:
        return []
    out: list[tuple[int, int]] = []
    for dr, dc in piece_dirs(piece):
        rr, cc = r + dr, c + dc
        if in_bounds(rr, cc, SIZE, SIZE) and not board[rr][cc]:
            out.append((rr, cc))
    return out


def _any_jumps_for_color(board: list[list[str]], color: str) -> bool:
    for r in range(SIZE):
        for c in range(SIZE):
            p = board[r][c]
            if p and piece_color(p) == color and _piece_jumps(board, r, c):
                return True
    return False


def _any_moves_for_color(board: list[list[str]], color: str) -> bool:
    if _any_jumps_for_color(board, color):
        return True
    for r in range(SIZE):
        for c in range(SIZE):
            p = board[r][c]
            if p and piece_color(p) == color and _piece_steps(board, r, c):
                return True
    return False


def _legal_destinations(state: dict[str, Any], r: int, c: int) -> list[tuple[int, int]]:
    """Destinations for (r,c), respecting forced-capture and mid-jump continuation."""
    board = state["board"]
    piece = board[r][c]
    if not piece:
        return []
    tp = state.get("turn_player")
    if piece_color(piece) != state.get("marks", {}).get(tp):
        return []
    cont = state.get("continue_from")
    if cont is not None:
        if [r, c] != [int(cont[0]), int(cont[1])]:
            return []
        return [(jr, jc) for jr, jc, _, _ in _piece_jumps(board, r, c)]
    if _any_jumps_for_color(board, piece_color(piece)):
        return [(jr, jc) for jr, jc, _, _ in _piece_jumps(board, r, c)]
    return _piece_steps(board, r, c)


class Checkers:
    id = "checkers"
    name = "Checkers"
    min_players = 2
    max_players = 2

    # ---------- lifecycle ----------

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 2:
            raise ValueError("checkers requires exactly 2 players")
        p1, p2 = players
        return {
            "board": _initial_board(),
            "marks": {p1: RED, p2: WHITE},
            "order": [p1, p2],
            "turn_player": p1,
            "winner": None,
            "continue_from": None,
            "last_move": None,
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if self.is_terminal(state):
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")
        if action.get("type") != "move":
            raise IllegalAction(f"expected move, got {action.get('type')}")
        try:
            fr = int(action["from"][0])
            fc = int(action["from"][1])
            tr = int(action["to"][0])
            tc = int(action["to"][1])
        except (KeyError, TypeError, ValueError, IndexError) as e:
            raise IllegalAction(f"bad move action: {action}") from e
        if not (in_bounds(fr, fc, SIZE, SIZE) and in_bounds(tr, tc, SIZE, SIZE)):
            raise IllegalAction(f"out of bounds: ({fr},{fc})->({tr},{tc})")

        board = state["board"]
        piece = board[fr][fc]
        if not piece:
            raise IllegalAction(f"no piece at ({fr},{fc})")
        color = state["marks"][player]
        if piece_color(piece) != color:
            raise IllegalAction(f"{piece} is not yours")

        cont = state.get("continue_from")
        if cont is not None and [fr, fc] != [int(cont[0]), int(cont[1])]:
            raise IllegalAction(f"must continue jumping from {list(cont)}")

        forced = cont is not None or _any_jumps_for_color(board, color)
        jumps = _piece_jumps(board, fr, fc)
        new_board = copy_grid(board)
        captured_rc: list[int] | None = None

        if forced:
            match = next((j for j in jumps if (j[0], j[1]) == (tr, tc)), None)
            if match is None:
                raise IllegalAction(
                    f"must capture: no jump from ({fr},{fc}) to ({tr},{tc})"
                )
            _, _, cap_r, cap_c = match
            new_board[cap_r][cap_c] = EMPTY_CELL
            captured_rc = [cap_r, cap_c]
        else:
            if (tr, tc) not in _piece_steps(board, fr, fc):
                raise IllegalAction(f"illegal step ({fr},{fc})->({tr},{tc})")

        new_board[fr][fc] = EMPTY_CELL
        moved = piece
        promoted = False
        if not is_king(piece) and tr == _king_row_for(color):
            moved = RED_KING if color == RED else WHITE_KING
            promoted = True
        new_board[tr][tc] = moved

        new_cont: list[int] | None = None
        next_turn = opponent_of(state["order"], player)
        if forced and not promoted and _piece_jumps(new_board, tr, tc):
            new_cont = [tr, tc]
            next_turn = player

        new_state = {
            **state,
            "board": new_board,
            "turn_player": next_turn,
            "continue_from": new_cont,
            "last_move": {
                "from": [fr, fc],
                "to": [tr, tc],
                "captured": captured_rc,
                "promoted": promoted,
            },
        }
        if new_cont is None:
            opp_color = state["marks"][next_turn]
            if not _any_moves_for_color(new_board, opp_color):
                new_state["winner"] = player
        return new_state

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
            "mode": "select",
            "row": 5,
            "col": 0,
            "from": None,
            "viewer_seat": 0,
        }

    def init_cursor_for(self, me: str, state: dict[str, Any]) -> dict[str, Any]:
        order = state.get("order", [])
        try:
            seat = order.index(me)
        except ValueError:
            seat = 0
        row, col = (5, 0) if seat == 0 else (2, 1)
        return {
            **self.initial_cursor(),
            "row": row,
            "col": col,
            "viewer_seat": seat,
        }

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        dr, dc = _ARROW_TO_DIAG.get((dr, dc), (dr, dc))
        if cursor.get("viewer_seat", 0) == 1:
            dr, dc = -dr, -dc
        return wrap_cursor(cursor, dr, dc, SIZE, SIZE)

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        if cursor["mode"] != "target":
            raise IllegalAction("no piece selected")
        frm = cursor.get("from")
        if frm is None:
            raise IllegalAction("no piece selected")
        return {
            "type": "move",
            "from": [int(frm[0]), int(frm[1])],
            "to": [int(cursor["row"]), int(cursor["col"])],
        }

    def stage_cursor(self, cursor: dict[str, Any]) -> dict[str, Any]:
        if cursor["mode"] == "select":
            return {
                **cursor,
                "mode": "target",
                "from": [cursor["row"], cursor["col"]],
            }
        frm = cursor.get("from")
        row, col = (
            (int(frm[0]), int(frm[1]))
            if frm is not None
            else (cursor["row"], cursor["col"])
        )
        return {**cursor, "mode": "select", "row": row, "col": col, "from": None}

    def sync_cursor(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        cont = state.get("continue_from")
        if cont is not None:
            return {
                **cursor,
                "mode": "select",
                "row": int(cont[0]),
                "col": int(cont[1]),
                "from": None,
            }
        if cursor["mode"] == "select":
            return cursor
        return {**cursor, "mode": "select", "from": None}

    # ---------- animation ----------

    def animation_for(
        self, prev_state: dict[str, Any], new_state: dict[str, Any]
    ) -> None:
        return None

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
        theme = ui.get("theme")
        me = ui.get("player")

        board = state["board"]
        order = state.get("order", [])
        marks = state.get("marks", {})
        flipped = int(cursor.get("viewer_seat", 0)) == 1

        def to_board(dr: int, dc: int) -> tuple[int, int]:
            return (SIZE - 1 - dr, SIZE - 1 - dc) if flipped else (dr, dc)

        grid_style = style(theme, "primary")
        # Labels and counts sit on the canvas (surface) — contrast auto-picks
        # a legible fg no matter which theme is active.
        header_style = contrast_style(theme, "surface", bold=True)
        hint_style = style(theme, "success", bold=True)
        red_style = style(theme, "error", bold=True)
        white_style = style(theme, "accent", bold=True)
        # Derive board squares from the surface color by shifting luminance in
        # both directions — this tracks light and dark themes symmetrically
        # instead of reading a text color (which inverts on light themes).
        dark_hex = shifted_color(theme, "surface", -0.18)
        light_hex = shifted_color(theme, "surface", 0.12)
        dark_bg = Style(bgcolor=dark_hex)
        light_bg = Style(bgcolor=light_hex)
        dark_neutral = contrast_on_hex(dark_hex, dim=True) + dark_bg
        cursor_active, cursor_inactive = cursor_palette(theme)

        mode = cursor.get("mode", "select")
        cur_r = int(cursor.get("row", 0))
        cur_c = int(cursor.get("col", 0))
        frm = cursor.get("from")
        from_rc: tuple[int, int] | None = None
        if frm is not None:
            from_rc = (int(frm[0]), int(frm[1]))

        legal_set: set[tuple[int, int]] = set()
        if (
            from_rc is not None
            and me is not None
            and state.get("turn_player") == me
            and not self.is_terminal(state)
        ):
            legal_set = set(_legal_destinations(state, from_rc[0], from_rc[1]))

        last_move = state.get("last_move") or {}
        last_from = (
            (int(last_move["from"][0]), int(last_move["from"][1]))
            if last_move.get("from")
            else None
        )
        last_to = (
            (int(last_move["to"][0]), int(last_move["to"][1]))
            if last_move.get("to")
            else None
        )

        cont = state.get("continue_from")
        cont_rc: tuple[int, int] | None = (int(cont[0]), int(cont[1])) if cont else None

        def piece_fg(p: str) -> Style:
            return red_style if piece_color(p) == RED else white_style

        def cell_segs(r: int, c: int) -> list[Segment]:
            piece = board[r][c]
            dark = _is_dark(r, c)
            bg = dark_bg if dark else light_bg
            glyph = GLYPHS.get(piece, " ") if piece else " "
            is_cursor = (r, c) == (cur_r, cur_c) and mode in ("select", "target")
            is_from = from_rc == (r, c)
            is_last = (r, c) == last_from or (r, c) == last_to
            is_hint = (r, c) in legal_set
            is_cont = cont_rc == (r, c)

            if is_cursor:
                return cursor_bracket(
                    glyph, cursor_active if active else cursor_inactive
                )
            if piece:
                fg = piece_fg(piece) + bg
                if is_from:
                    return [
                        Segment("(", hint_style + bg),
                        Segment(glyph, fg),
                        Segment(")", hint_style + bg),
                    ]
                if is_cont:
                    return [
                        Segment("<", hint_style + bg),
                        Segment(glyph, fg),
                        Segment(">", hint_style + bg),
                    ]
                return [Segment(" ", bg), Segment(glyph, fg), Segment(" ", bg)]
            if is_hint:
                return [
                    Segment(" ", bg),
                    Segment("∘", hint_style + bg),
                    Segment(" ", bg),
                ]
            if is_last and dark:
                return [
                    Segment(" ", bg),
                    Segment("·", dark_neutral),
                    Segment(" ", bg),
                ]
            return [Segment("   ", bg)]

        def grid_line(left: str, mid: str, right: str) -> Strip:
            body = left + ("───" + mid) * (SIZE - 1) + "───" + right
            return Strip([Segment("   ", header_style), Segment(body, grid_style)])

        def file_label_strip() -> Strip:
            segs: list[Segment] = [Segment("    ")]
            for dc in range(SIZE):
                _, bc = to_board(0, dc)
                segs.append(Segment(f" {chr(ord('a') + bc)}  ", header_style))
            return Strip(segs)

        def row_strip(dr: int) -> Strip:
            br, _ = to_board(dr, 0)
            rank = str(SIZE - br)
            segs: list[Segment] = [
                Segment(f" {rank} ", header_style),
                Segment("│", grid_style),
            ]
            for dc in range(SIZE):
                _, bc = to_board(dr, dc)
                segs.extend(cell_segs(br, bc))
                segs.append(Segment("│", grid_style))
            return Strip(segs)

        parts: list[Segment] = [Segment("  ", header_style)]
        for p in order:
            tag = marks.get(p, "?")
            glyph = GLYPHS.get(tag, tag)
            fg = red_style if tag in (RED, RED_KING) else white_style
            parts.append(Segment(f"{p}(", header_style))
            parts.append(Segment(glyph, fg))
            parts.append(Segment(")  ", header_style))
        lines: list[Strip] = [
            Strip(parts),
            file_label_strip(),
            grid_line("┌", "┬", "┐"),
        ]
        for dr in range(SIZE):
            lines.append(row_strip(dr))
            if dr < SIZE - 1:
                lines.append(grid_line("├", "┼", "┤"))
        lines.append(grid_line("└", "┴", "┘"))
        lines.append(file_label_strip())

        reds = sum(1 for row in board for p in row if piece_color(p) == RED)
        whites = sum(1 for row in board for p in row if piece_color(p) == WHITE)
        lines.append(Strip([Segment("")]))
        lines.append(
            Strip(
                [
                    Segment("  ", header_style),
                    Segment("●", red_style),
                    Segment(f" {reds}   ", header_style),
                    Segment("●", white_style),
                    Segment(f" {whites}", header_style),
                ]
            )
        )
        lines.append(status_strip(self._status(state, cursor, me)))
        return lines

    def _status(
        self,
        state: dict[str, Any],
        cursor: dict[str, Any],
        me: str | None,
    ) -> str:
        winner = state.get("winner")
        if winner:
            return f"  winner: {winner}"
        turn = state.get("turn_player")
        mark = state.get("marks", {}).get(turn, "?")
        base = f"  turn: {turn} ({GLYPHS.get(mark, mark)})"
        if state.get("continue_from"):
            base += "  — must continue jumping"
        if me == turn:
            mode = cursor.get("mode", "select")
            if mode == "select":
                base += "  — space: pick piece"
            elif mode == "target":
                base += "  — enter: move, space: cancel"
        return base

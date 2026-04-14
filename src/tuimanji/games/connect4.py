from typing import Any

from rich.segment import Segment
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import style
from ._common import (
    EMPTY,
    col_labels,
    copy_grid,
    empty_grid,
    grid_bot,
    grid_sep,
    grid_top,
    header_palette,
    opponent_of,
    order_header,
    status_strip,
)

ROWS = 6
COLS = 7
DIRS = [(0, 1), (1, 0), (1, 1), (1, -1)]


class Connect4:
    id = "connect-4"
    name = "Connect 4"
    min_players = 2
    max_players = 2

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 2:
            raise ValueError("connect-4 requires exactly 2 players")
        return {
            "board": empty_grid(ROWS, COLS),
            "marks": {players[0]: "R", players[1]: "Y"},
            "order": list(players),
            "turn_player": players[0],
            "winner": None,
            "last_drop": None,  # (row, col) of most recent chip, for animation diffs
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if state.get("winner") is not None or self._is_draw(state):
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")
        try:
            col = int(action["col"])
        except (KeyError, TypeError, ValueError) as e:
            raise IllegalAction(f"bad action: {action}") from e
        if not (0 <= col < COLS):
            raise IllegalAction(f"column out of bounds: {col}")
        board = copy_grid(state["board"])
        target_row = self._lowest_empty(board, col)
        if target_row is None:
            raise IllegalAction(f"column {col} is full")
        mark = state["marks"][player]
        board[target_row][col] = mark
        next_player = opponent_of(state["order"], player)
        return {
            **state,
            "board": board,
            "turn_player": next_player,
            "winner": self._check_winner(board, state["marks"]),
            "last_drop": [target_row, col],
        }

    def _lowest_empty(self, board: list[list[str]], col: int) -> int | None:
        for r in range(ROWS - 1, -1, -1):
            if board[r][col] == EMPTY:
                return r
        return None

    def _check_winner(
        self, board: list[list[str]], marks: dict[str, str]
    ) -> str | None:
        inv = {v: k for k, v in marks.items()}
        for r in range(ROWS):
            for c in range(COLS):
                cell = board[r][c]
                if cell == EMPTY:
                    continue
                for dr, dc in DIRS:
                    if all(
                        0 <= r + dr * k < ROWS
                        and 0 <= c + dc * k < COLS
                        and board[r + dr * k][c + dc * k] == cell
                        for k in range(4)
                    ):
                        return inv[cell]
        return None

    def _is_draw(self, state: dict[str, Any]) -> bool:
        return state.get("winner") is None and all(
            cell != EMPTY for row in state["board"] for cell in row
        )

    def current_player(self, state: dict[str, Any]) -> str | None:
        if self.is_terminal(state):
            return None
        return state["turn_player"]

    def winner(self, state: dict[str, Any]) -> str | None:
        return state.get("winner")

    def is_terminal(self, state: dict[str, Any]) -> bool:
        return state.get("winner") is not None or self._is_draw(state)

    def initial_cursor(self) -> dict[str, Any]:
        return {"row": 0, "col": 0}

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        return {"row": 0, "col": (cursor["col"] + dc) % COLS}

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        return {"col": cursor["col"]}

    def animation_for(
        self, prev_state: dict[str, Any], new_state: dict[str, Any]
    ) -> dict[str, Any] | None:
        drop = new_state.get("last_drop")
        if drop is None:
            return None
        target_row, col = drop
        prev_board = prev_state.get("board")
        if prev_board is None:
            return None
        # Sanity check: the target cell must have been empty in prev.
        if prev_board[target_row][col] != EMPTY:
            return None
        mark = new_state["board"][target_row][col]
        return {"type": "fall", "col": col, "target_row": target_row, "mark": mark}

    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]:
        ui = ui or {}
        cursor = ui.get("cursor")
        active = ui.get("active", True)
        falling = ui.get("falling")  # {"col": c, "row": r, "mark": m} or None
        theme = ui.get("theme")

        board = state["board"]

        empty_style = style(theme, "muted")
        grid_style = style(theme, "primary")
        cursor_active = style(theme, "success", bold=True)
        cursor_inactive = style(theme, "muted")
        header_style = header_palette(theme)
        chip_style = {
            "R": style(theme, "error", bold=True),
            "Y": style(theme, "warning", bold=True),
        }

        def chip_segment(ch: str) -> Segment:
            if ch == EMPTY:
                return Segment("·", empty_style)
            return Segment("●", chip_style[ch])

        def draw_row(row_idx: int) -> Strip:
            segs: list[Segment] = [Segment("│", grid_style)]
            for c in range(COLS):
                cell = board[row_idx][c]
                # Overlay the falling chip if it's currently at this cell.
                if (
                    falling is not None
                    and falling["col"] == c
                    and falling["row"] == row_idx
                ):
                    segs.append(Segment(" "))
                    segs.append(chip_segment(falling["mark"]))
                    segs.append(Segment(" "))
                else:
                    segs.append(Segment(" "))
                    segs.append(chip_segment(cell))
                    segs.append(Segment(" "))
                segs.append(Segment("│", grid_style))
            return Strip(segs)

        header = order_header(state, header_style)

        # Cursor row above the board — an arrow over the selected column.
        cursor_row_segs: list[Segment] = [Segment(" ")]
        cursor_style = cursor_active if active else cursor_inactive
        for c in range(COLS):
            is_sel = cursor is not None and cursor.get("col") == c
            glyph = "▼" if is_sel else " "
            cursor_row_segs.append(Segment(" "))
            cursor_row_segs.append(Segment(glyph, cursor_style))
            cursor_row_segs.append(Segment(" "))
            cursor_row_segs.append(Segment(" "))
        cursor_line = Strip(cursor_row_segs)

        lines: list[Strip] = [header, cursor_line, grid_top(COLS, grid_style)]
        for r in range(ROWS):
            lines.append(draw_row(r))
            if r < ROWS - 1:
                lines.append(grid_sep(COLS, grid_style))
        lines.append(grid_bot(COLS, grid_style))
        lines.append(col_labels(COLS, header_style, start=1))

        if state.get("winner") is not None:
            status = f"  winner: {state['winner']}"
        elif self._is_draw(state):
            status = "  draw"
        else:
            status = f"  turn: {state.get('turn_player')}"
        lines.append(Strip([Segment("")]))
        lines.append(status_strip(status))
        return lines

from typing import Any

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction

ROWS = 6
COLS = 7
EMPTY = "."
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
            "board": [[EMPTY] * COLS for _ in range(ROWS)],
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
        board = [row[:] for row in state["board"]]
        target_row = self._lowest_empty(board, col)
        if target_row is None:
            raise IllegalAction(f"column {col} is full")
        mark = state["marks"][player]
        board[target_row][col] = mark
        order = state["order"]
        next_player = order[(order.index(player) + 1) % 2]
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

        board = state["board"]
        marks = state.get("marks", {})

        red_style = Style(color="bright_red", bold=True)
        yellow_style = Style(color="bright_yellow", bold=True)
        empty_style = Style(color="grey23")
        grid_style = Style(color="blue")
        cursor_active = Style(color="bright_green", bold=True)
        cursor_inactive = Style(color="grey50")
        header_style = Style(dim=True)
        chip_style = {"R": red_style, "Y": yellow_style}

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

        header_text = "  "
        for p in state.get("order", []):
            header_text += f"{p}({marks.get(p, '?')})  "
        header = Strip([Segment(header_text, header_style)])

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

        top = Strip([Segment("┌" + "───┬" * (COLS - 1) + "───┐", grid_style)])
        sep = Strip([Segment("├" + "───┼" * (COLS - 1) + "───┤", grid_style)])
        bot = Strip([Segment("└" + "───┴" * (COLS - 1) + "───┘", grid_style)])

        lines: list[Strip] = [header, cursor_line, top]
        for r in range(ROWS):
            lines.append(draw_row(r))
            if r < ROWS - 1:
                lines.append(sep)
        lines.append(bot)

        # Column labels
        label_segs: list[Segment] = [Segment(" ")]
        for c in range(COLS):
            label_segs.append(Segment(" "))
            label_segs.append(Segment(str(c + 1), header_style))
            label_segs.append(Segment(" "))
            label_segs.append(Segment(" "))
        lines.append(Strip(label_segs))

        turn = state.get("turn_player")
        w = state.get("winner")
        if w is not None:
            status = f"  winner: {w}"
        elif self._is_draw(state):
            status = "  draw"
        else:
            status = f"  turn: {turn}"
        lines.append(Strip([Segment("")]))
        lines.append(Strip([Segment(status, Style(italic=True))]))
        return lines

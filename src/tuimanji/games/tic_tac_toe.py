from typing import Any

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import bg_style, style

EMPTY = "."
LINES = [
    [(0, 0), (0, 1), (0, 2)],
    [(1, 0), (1, 1), (1, 2)],
    [(2, 0), (2, 1), (2, 2)],
    [(0, 0), (1, 0), (2, 0)],
    [(0, 1), (1, 1), (2, 1)],
    [(0, 2), (1, 2), (2, 2)],
    [(0, 0), (1, 1), (2, 2)],
    [(0, 2), (1, 1), (2, 0)],
]


class TicTacToe:
    id = "tic-tac-toe"
    name = "Tic-Tac-Toe"
    min_players = 2
    max_players = 2

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 2:
            raise ValueError("tic-tac-toe requires exactly 2 players")
        return {
            "board": [[EMPTY] * 3 for _ in range(3)],
            "marks": {players[0]: "X", players[1]: "O"},
            "order": list(players),
            "turn_player": players[0],
            "winner": None,
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if state.get("winner") is not None or self._is_draw(state):
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")
        try:
            r, c = int(action["row"]), int(action["col"])
        except (KeyError, TypeError, ValueError) as e:
            raise IllegalAction(f"bad action: {action}") from e
        if not (0 <= r < 3 and 0 <= c < 3):
            raise IllegalAction(f"out of bounds: ({r},{c})")
        board = [row[:] for row in state["board"]]
        if board[r][c] != EMPTY:
            raise IllegalAction(f"cell ({r},{c}) is taken")
        board[r][c] = state["marks"][player]
        order = state["order"]
        next_player = order[(order.index(player) + 1) % 2]
        new_state = {
            **state,
            "board": board,
            "turn_player": next_player,
            "winner": self._check_winner(board, state["marks"]),
        }
        return new_state

    def _check_winner(
        self, board: list[list[str]], marks: dict[str, str]
    ) -> str | None:
        inv = {v: k for k, v in marks.items()}
        for line in LINES:
            vals = [board[r][c] for r, c in line]
            if vals[0] != EMPTY and vals[0] == vals[1] == vals[2]:
                return inv[vals[0]]
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
        return {
            "row": (cursor["row"] + dr) % 3,
            "col": (cursor["col"] + dc) % 3,
        }

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        return {"row": cursor["row"], "col": cursor["col"]}

    def animation_for(
        self, prev_state: dict[str, Any], new_state: dict[str, Any]
    ) -> dict[str, Any] | None:
        return None

    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]:
        board = state["board"]
        marks = state.get("marks", {})
        ui = ui or {}
        cur = ui.get("cursor")
        cursor = (cur["row"], cur["col"]) if cur is not None else None
        active = ui.get("active", True)
        theme = ui.get("theme")

        x_style = style(theme, "primary", bold=True)
        o_style = style(theme, "accent", bold=True)
        grid_style = style(theme, "muted")
        cursor_active = bg_style(theme, "warning", color="black", bold=True)
        cursor_inactive = bg_style(theme, "muted", color="white")
        styles = {"X": x_style, "O": o_style, EMPTY: style(theme, "muted")}

        def cell_strip(row_idx: int) -> Strip:
            segs: list[Segment] = []
            for c in range(3):
                ch = board[row_idx][c]
                glyph = ch if ch != EMPTY else "·"
                is_cursor = cursor == (row_idx, c)
                if is_cursor:
                    bg = cursor_active if active else cursor_inactive
                    segs.append(Segment("[", bg))
                    segs.append(Segment(glyph, bg))
                    segs.append(Segment("]", bg))
                else:
                    segs.append(Segment(" "))
                    segs.append(Segment(glyph, styles[ch]))
                    segs.append(Segment(" "))
                if c < 2:
                    segs.append(Segment("│", grid_style))
            return Strip(segs)

        sep = Strip([Segment("───┼───┼───", grid_style)])
        header_text = "  "
        for p in state.get("order", []):
            header_text += f"{p}({marks.get(p, '?')})  "
        header = Strip([Segment(header_text, Style(dim=True))])
        blank = Strip([Segment("")])

        lines: list[Strip] = [header, blank]
        for r in range(3):
            lines.append(cell_strip(r))
            if r < 2:
                lines.append(sep)

        turn = state.get("turn_player")
        w = state.get("winner")
        if w is not None:
            status = f"  winner: {w}"
        elif self._is_draw(state):
            status = "  draw"
        else:
            status = f"  turn: {turn}"
        lines.append(blank)
        lines.append(Strip([Segment(status, Style(italic=True))]))
        return lines

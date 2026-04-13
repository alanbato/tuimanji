from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from .. import store
from ..db import engine_for
from ..engine import GameError, NotYourTurn
from ..games import get as get_game
from .canvas import GameCanvas

if TYPE_CHECKING:
    from ..app import TuimanjiApp


class MatchScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Lobby"),
        Binding("up", "move(-1,0)", "Up"),
        Binding("down", "move(1,0)", "Down"),
        Binding("left", "move(0,-1)", "Left"),
        Binding("right", "move(0,1)", "Right"),
        Binding("enter", "place", "Place"),
    ]

    CSS = """
    MatchScreen { align: center middle; }
    #status { height: 3; padding: 1 2; }
    #error { height: 1; padding: 0 2; color: $error; }
    GameCanvas { border: round $primary; width: 40; height: 15; }
    """

    def __init__(self, game_id: str, match_id: str) -> None:
        super().__init__()
        self.game_id = game_id
        self.match_id = match_id
        self.game = get_game(game_id)
        self.engine = engine_for(game_id)
        self.canvas: GameCanvas | None = None
        self.cursor_row = 0
        self.cursor_col = 0
        self._last_turn = -1
        self._last_active: bool | None = None
        self._status: Static | None = None
        self._error_label: Static | None = None

    @property
    def _app(self) -> "TuimanjiApp":
        return cast("TuimanjiApp", self.app)

    @property
    def me(self) -> str:
        return self._app.player_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            self._status = Static("Loading…", id="status")
            yield self._status
            with Horizontal():
                latest = store.latest_state(self.engine, self.match_id)
                if latest is None:
                    raise RuntimeError(
                        f"MatchScreen opened for un-started match {self.match_id}"
                    )
                self.canvas = GameCanvas(self.game, latest.state)
                yield self.canvas
            self._error_label = Static("", id="error")
            yield self._error_label
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(0.5, self._refresh)

    def _push_cursor(self) -> None:
        if self.canvas is not None:
            self.canvas.set_ui(cursor=(self.cursor_row, self.cursor_col))

    def _refresh(self) -> None:
        latest = store.latest_state(self.engine, self.match_id)
        if latest is None:
            return
        if latest.turn != self._last_turn:
            self._last_turn = latest.turn
            if self.canvas is not None:
                self.canvas.set_state(latest.state)
        my_turn = latest.current == self.me and not self.game.is_terminal(latest.state)
        if my_turn != self._last_active:
            self._last_active = my_turn
            if self.canvas is not None:
                self.canvas.set_ui(
                    cursor=(self.cursor_row, self.cursor_col), active=my_turn
                )
        if latest.winner is not None:
            msg = f"  winner: {latest.winner} — press Esc to return to lobby"
        elif self.game.is_terminal(latest.state):
            msg = "  draw — press Esc to return to lobby"
        elif my_turn:
            msg = f"  your turn ({self.game.name})"
        else:
            msg = f"  waiting for {latest.current}…"
        if self._status:
            self._status.update(msg)

    def action_move(self, dr: int, dc: int) -> None:
        self.cursor_row = (self.cursor_row + dr) % 3
        self.cursor_col = (self.cursor_col + dc) % 3
        self._push_cursor()

    def action_place(self) -> None:
        try:
            store.submit_action(
                self.engine,
                self.match_id,
                self.me,
                {"row": self.cursor_row, "col": self.cursor_col},
                self.game,
            )
            if self._error_label:
                self._error_label.update("")
        except NotYourTurn:
            if self._error_label:
                self._error_label.update("not your turn")
        except GameError as e:
            if self._error_label:
                self._error_label.update(str(e))
        self._refresh()

    def action_back(self) -> None:
        self.app.pop_screen()

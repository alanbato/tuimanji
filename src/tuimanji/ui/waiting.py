from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from .. import store
from ..db import engine_for
from ..games import get as get_game
from ..store import MatchNotReady
from .match import MatchScreen

if TYPE_CHECKING:
    from ..app import TuimanjiApp


class WaitingRoomScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Lobby"),
        Binding("s", "start", "Start"),
    ]

    CSS = """
    WaitingRoomScreen { align: center middle; }
    #title { height: 3; padding: 1 2; text-style: bold; }
    #players { border: round $primary; width: 48; height: 10; padding: 0 1; }
    #hint { height: 1; padding: 0 2; color: $accent; }
    #error { height: 1; padding: 0 2; color: $error; }
    """

    def __init__(self, game_id: str, match_id: str) -> None:
        super().__init__()
        self.game_id = game_id
        self.match_id = match_id
        self.game = get_game(game_id)
        self.engine = engine_for(game_id)
        self._players_label: Static | None = None
        self._title: Static | None = None
        self._hint: Static | None = None
        self._error: Static | None = None
        self._last_snapshot: tuple[str, ...] = ()

    @property
    def _app(self) -> "TuimanjiApp":
        return cast("TuimanjiApp", self.app)

    @property
    def me(self) -> str:
        return self._app.player_id

    @property
    def is_host(self) -> bool:
        match = store.get_match(self.engine, self.match_id)
        return match is not None and match.created_by == self.me

    def compose(self) -> ComposeResult:
        with Vertical():
            self._title = Static(f"Waiting room — {self.game.name}", id="title")
            yield self._title
            self._players_label = Static("", id="players")
            yield self._players_label
            self._hint = Static("", id="hint")
            yield self._hint
            self._error = Static("", id="error")
            yield self._error
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(0.5, self._refresh)

    def _refresh(self) -> None:
        match = store.get_match(self.engine, self.match_id)
        if match is None:
            self.app.pop_screen()
            return
        if match.status == "active":
            # Someone started it — transition into the match screen.
            self.app.switch_screen(MatchScreen(self.game_id, self.match_id))
            return
        players = store.match_players(self.engine, self.match_id)
        snapshot = tuple(players)
        if snapshot != self._last_snapshot:
            self._last_snapshot = snapshot
            if self._players_label:
                lines = []
                for i, p in enumerate(players):
                    marker = " (host)" if p == match.created_by else ""
                    lines.append(f"  {i + 1}. {p}{marker}")
                for i in range(len(players), self.game.max_players):
                    lines.append(f"  {i + 1}. (open)")
                self._players_label.update("\n".join(lines))
        if self._hint:
            needed = max(0, self.game.min_players - len(players))
            if needed > 0:
                self._hint.update(f"  waiting for {needed} more player(s)…")
            elif self.is_host:
                self._hint.update("  press s to start")
            else:
                self._hint.update("  waiting for host to start…")

    def action_start(self) -> None:
        try:
            store.start_match(self.engine, self.game, self.match_id, self.me)
        except MatchNotReady as e:
            if self._error:
                self._error.update(str(e))
            return
        except ValueError as e:
            if self._error:
                self._error.update(str(e))
            return
        self._refresh()

    def action_back(self) -> None:
        self.app.pop_screen()

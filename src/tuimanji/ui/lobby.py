from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, ListItem, ListView, Static

from .. import store
from ..db import engine_for
from ..games import REGISTRY, all_games
from .match import MatchScreen

if TYPE_CHECKING:
    from ..app import TuimanjiApp


class LobbyScreen(Screen):
    BINDINGS = [
        Binding("n", "new_match", "New"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    CSS = """
    LobbyScreen { layout: vertical; }
    #title { height: 3; padding: 1 2; text-style: bold; }
    #panes { height: 1fr; }
    #games, #matches { width: 1fr; border: round $primary; }
    ListView { height: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._game_ids: list[str] = [g.id for g in all_games()]
        self.selected_game_id: str = self._game_ids[0]
        self._games_list: ListView | None = None
        self._matches_list: ListView | None = None
        self._match_ids: list[str] = []
        self._last_snapshot: tuple[tuple[str, str, str], ...] = ()

    @property
    def _app(self) -> "TuimanjiApp":
        return cast("TuimanjiApp", self.app)

    @property
    def me(self) -> str:
        return self._app.player_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Tuimanji — welcome, {self.me}", id="title")
        with Horizontal(id="panes"):
            with Vertical(id="games"):
                yield Static("Games")
                items = [ListItem(Static(g.name)) for g in all_games()]
                self._games_list = ListView(*items)
                yield self._games_list
            with Vertical(id="matches"):
                yield Static("Matches")
                self._matches_list = ListView()
                yield self._matches_list
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_matches()
        self.set_interval(1.0, self._refresh_matches)

    def _refresh_matches(self) -> None:
        if self._matches_list is None:
            return
        engine = engine_for(self.selected_game_id)
        rows = store.list_matches(engine)
        snapshot = tuple(
            (m.id, m.status, "+".join(store.match_players(engine, m.id))) for m in rows
        )
        if snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot
        self._match_ids = [m.id for m in rows]
        self._matches_list.clear()
        for m_id, status, players in snapshot:
            label = f"[{status}] {m_id}  {players or '(empty)'}"
            self._matches_list.append(ListItem(Static(label)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        list_view = event.list_view
        index = event.list_view.index
        if list_view is self._games_list and index is not None:
            self.selected_game_id = self._game_ids[index]
            self._last_snapshot = ()  # force refresh
            self._refresh_matches()
        elif list_view is self._matches_list and index is not None:
            if 0 <= index < len(self._match_ids):
                self._join_and_enter(self._match_ids[index])

    def _join_and_enter(self, match_id: str) -> None:
        engine = engine_for(self.selected_game_id)
        game = REGISTRY[self.selected_game_id]
        try:
            store.join_match(engine, game, match_id, self.me)
        except Exception as e:
            self.notify(f"join failed: {e}", severity="error")
            return
        self.app.push_screen(MatchScreen(self.selected_game_id, match_id))

    def action_new_match(self) -> None:
        engine = engine_for(self.selected_game_id)
        game = REGISTRY[self.selected_game_id]
        match_id = store.create_match(engine, game, self.me)
        self.notify(f"created match {match_id}")
        self._refresh_matches()

    def action_refresh(self) -> None:
        self._refresh_matches()

    def action_quit(self) -> None:
        self.app.exit()

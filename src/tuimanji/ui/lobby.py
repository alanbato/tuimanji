from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, ListItem, ListView, Static

from .. import store
from ..db import engine_for
from ..games import REGISTRY, all_games
from .match import MatchScreen
from .waiting import WaitingRoomScreen

if TYPE_CHECKING:
    from ..app import TuimanjiApp


_STATUS_STYLE = {
    "waiting": ("yellow", "◔"),
    "active": ("bright_green", "●"),
    "finished": ("grey50", "✓"),
}


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
    #games { width: 30; border: round $primary; }
    #matches { width: 1fr; border: round $primary; }
    ListView { height: 1fr; }
    DataTable { height: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._game_ids: list[str] = [g.id for g in all_games()]
        self.selected_game_id: str = self._game_ids[0]
        self._games_list: ListView | None = None
        self._matches_table: DataTable[Text] | None = None
        self._match_ids: list[str] = []
        self._last_snapshot: tuple[tuple[str, str, int, int, tuple[str, ...]], ...] = ()
        self._last_games_counts: tuple[tuple[int, int], ...] = ()

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
                yield Static("[b]Games[/b]", markup=True)
                items = [ListItem(Static(g.name, markup=True)) for g in all_games()]
                self._games_list = ListView(*items)
                yield self._games_list
            with Vertical(id="matches"):
                yield Static("[b]Matches[/b]", markup=True)
                table: DataTable[Text] = DataTable(
                    cursor_type="row", zebra_stripes=True
                )
                table.add_columns("Status", "Seats", "ID", "Players")
                self._matches_table = table
                yield table
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(1.0, self._refresh)

    def _refresh(self) -> None:
        self._refresh_games()
        self._refresh_matches()

    def _refresh_games(self) -> None:
        if self._games_list is None:
            return
        counts: list[tuple[int, int]] = []
        for gid in self._game_ids:
            engine = engine_for(gid)
            rows = store.list_matches(engine)
            live = sum(1 for m in rows if m.status != "finished")
            done = sum(1 for m in rows if m.status == "finished")
            counts.append((live, done))
        counts_t = tuple(counts)
        if counts_t == self._last_games_counts:
            return
        self._last_games_counts = counts_t
        games = list(all_games())
        for i, child in enumerate(self._games_list.children):
            if not isinstance(child, ListItem):
                continue
            static = child.query_one(Static)
            live, done = counts[i]
            suffix_parts: list[str] = []
            if live:
                suffix_parts.append(f"[bright_green]{live} live[/bright_green]")
            if done:
                suffix_parts.append(f"[grey50]{done} done[/grey50]")
            suffix = f"  ({', '.join(suffix_parts)})" if suffix_parts else ""
            static.update(f"[b]{games[i].name}[/b]{suffix}")

    def _refresh_matches(self) -> None:
        if self._matches_table is None:
            return
        engine = engine_for(self.selected_game_id)
        game = REGISTRY[self.selected_game_id]
        rows = store.list_matches(engine)
        # Sort: waiting → active → finished, newest first within each bucket.
        bucket = {"waiting": 0, "active": 1, "finished": 2}
        rows.sort(key=lambda m: (bucket.get(m.status, 99), -m.created_at))
        snapshot = tuple(
            (
                m.id,
                m.status,
                len(store.match_players(engine, m.id)),
                game.max_players,
                tuple(store.match_players(engine, m.id)),
            )
            for m in rows
        )
        if snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot
        self._match_ids = [m.id for m in rows]
        self._matches_table.clear()
        for m_id, status, seated, cap, players in snapshot:
            color, glyph = _STATUS_STYLE.get(status, ("white", "?"))
            dim = status == "finished"
            status_cell = Text(f"{glyph} {status}", style=color)
            seats_color = (
                "grey50" if dim else ("bright_green" if seated == cap else "yellow")
            )
            seats_cell = Text(f"{seated}/{cap}", style=seats_color)
            id_cell = Text(m_id, style="grey50")
            players_str = ", ".join(players) if players else "(empty)"
            players_cell = Text(players_str, style="grey50" if dim else "white")
            self._matches_table.add_row(status_cell, seats_cell, id_cell, players_cell)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view is self._games_list and event.list_view.index is not None:
            self.selected_game_id = self._game_ids[event.list_view.index]
            self._last_snapshot = ()  # force rebuild of match list
            self._refresh_matches()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table is not self._matches_table:
            return
        index = event.cursor_row
        if 0 <= index < len(self._match_ids):
            self._join_and_enter(self._match_ids[index])

    def _join_and_enter(self, match_id: str) -> None:
        engine = engine_for(self.selected_game_id)
        game = REGISTRY[self.selected_game_id]
        match = store.get_match(engine, match_id)
        if match is None:
            self.notify("match no longer exists", severity="error")
            return
        if match.status == "waiting":
            try:
                store.join_match(engine, game, match_id, self.me)
            except Exception as e:
                self.notify(f"join failed: {e}", severity="error")
                return
            self.app.push_screen(WaitingRoomScreen(self.selected_game_id, match_id))
        elif match.status == "active":
            if self.me not in store.match_players(engine, match_id):
                self.notify("match already started", severity="warning")
                return
            self.app.push_screen(MatchScreen(self.selected_game_id, match_id))
        else:
            self.notify("match is finished", severity="information")

    def action_new_match(self) -> None:
        engine = engine_for(self.selected_game_id)
        game = REGISTRY[self.selected_game_id]
        match_id = store.create_match(engine, game, self.me)
        self.notify(f"created match {match_id}")
        self._refresh()
        self.app.push_screen(WaitingRoomScreen(self.selected_game_id, match_id))

    def action_refresh(self) -> None:
        self._refresh()

    def action_quit(self) -> None:
        self.app.exit()

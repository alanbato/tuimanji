from textual.app import App

from . import session, store
from .games import REGISTRY
from .identity import current_player
from .ui.lobby import LobbyScreen
from .ui.match import MatchScreen
from .ui.waiting import WaitingRoomScreen


class TuimanjiApp(App):
    TITLE = "Tuimanji"

    def __init__(
        self,
        resume: bool = False,
        new_game_id: str | None = None,
        join_match_id: str | None = None,
    ) -> None:
        super().__init__()
        self.unix_user = current_player()
        self.slot, self.player_id = session.acquire(self.unix_user)
        self.sub_title = self.player_id
        self._resume = resume
        self._new_game_id = new_game_id
        self._join_match_id = join_match_id

    def on_mount(self) -> None:
        self.push_screen(LobbyScreen())
        if self._new_game_id is not None:
            self._start_new_match(self._new_game_id)
            return
        if self._join_match_id is not None:
            self._join_match(self._join_match_id)
            return
        if self._resume:
            self._resume_last_match()

    def _start_new_match(self, game_id: str) -> None:
        game = REGISTRY[game_id]
        match_id = store.create_match(game, self.player_id)
        if game.max_players == 1:
            store.start_match(game, match_id, self.player_id)
            self.push_screen(MatchScreen(game_id, match_id))
            return
        self.push_screen(WaitingRoomScreen(game_id, match_id))

    def _join_match(self, match_id: str) -> None:
        game_id = store.find_match_game(match_id)
        if game_id is None:
            self.notify(f"match '{match_id}' not found", severity="error")
            return
        game = REGISTRY[game_id]
        match = store.get_match(match_id)
        if match is None or match.status == "finished":
            self.notify("match is finished", severity="information")
            return
        if match.status == "waiting":
            try:
                store.join_match(game, match_id, self.player_id)
            except Exception as e:
                self.notify(f"join failed: {e}", severity="error")
                return
            self.push_screen(WaitingRoomScreen(game_id, match_id))
            return
        if self.player_id not in store.match_players(match_id):
            self.notify("match already started", severity="warning")
            return
        self.push_screen(MatchScreen(game_id, match_id))

    def _resume_last_match(self) -> None:
        target = session.find_resume_target(self.player_id)
        if target is None:
            self.notify("nothing to resume", severity="information")
            return
        game_id, match_id, status = target
        if status == "active":
            self.push_screen(MatchScreen(game_id, match_id))
        else:
            self.push_screen(WaitingRoomScreen(game_id, match_id))

from textual.app import App

from . import session, store
from .db import engine_for
from .games import REGISTRY
from .identity import current_player
from .ui.lobby import LobbyScreen
from .ui.match import MatchScreen
from .ui.waiting import WaitingRoomScreen


class TuimanjiApp(App):
    TITLE = "Tuimanji"

    def __init__(self, resume: bool = False, new_game_id: str | None = None) -> None:
        super().__init__()
        self.unix_user = current_player()
        self.slot, self.player_id = session.acquire(self.unix_user)
        self.sub_title = self.player_id
        self._resume = resume
        self._new_game_id = new_game_id

    def on_mount(self) -> None:
        self.push_screen(LobbyScreen())
        if self._new_game_id is not None:
            self._start_new_match(self._new_game_id)
            return
        if self._resume:
            self._resume_last_match()

    def _start_new_match(self, game_id: str) -> None:
        game = REGISTRY[game_id]
        engine = engine_for(game_id)
        match_id = store.create_match(engine, game, self.player_id)
        self.push_screen(WaitingRoomScreen(game_id, match_id))

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

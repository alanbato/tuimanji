from textual.app import App

from . import session
from .identity import current_player
from .ui.lobby import LobbyScreen


class TuimanjiApp(App):
    TITLE = "Tuimanji"

    def __init__(self) -> None:
        super().__init__()
        self.unix_user = current_player()
        self.slot, self.player_id = session.acquire(self.unix_user)
        self.sub_title = self.player_id

    def on_mount(self) -> None:
        self.push_screen(LobbyScreen())

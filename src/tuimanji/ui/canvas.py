from typing import Any

from textual.strip import Strip
from textual.widget import Widget

from ..engine import Game


class GameCanvas(Widget, can_focus=True):
    DEFAULT_CSS = """
    GameCanvas {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    def __init__(self, game: Game, state: dict[str, Any]) -> None:
        super().__init__()
        self.game = game
        self._state = state
        self._lines: list[Strip] = []

    def set_state(self, state: dict[str, Any]) -> None:
        self._state = state
        self._lines = self.game.render(state, self.size)
        self.refresh()

    def on_mount(self) -> None:
        self._lines = self.game.render(self._state, self.size)
        self.refresh()

    def on_resize(self) -> None:
        self._lines = self.game.render(self._state, self.size)
        self.refresh()

    def render_line(self, y: int) -> Strip:
        if 0 <= y < len(self._lines):
            return self._lines[y].extend_cell_length(self.size.width)
        return Strip.blank(self.size.width)

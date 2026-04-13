from typing import Any, Protocol, runtime_checkable

from rich.segment import Segment  # noqa: F401  (used by Game impls)
from textual.geometry import Size
from textual.strip import Strip


class GameError(Exception):
    pass


class IllegalAction(GameError):
    pass


class NotYourTurn(GameError):
    def __init__(self, player: str, expected: str | None):
        super().__init__(f"not {player}'s turn (expected {expected})")
        self.player = player
        self.expected = expected


class MatchNotFound(GameError):
    pass


@runtime_checkable
class Game(Protocol):
    id: str
    name: str
    min_players: int
    max_players: int

    def initial_state(self, players: list[str]) -> dict[str, Any]: ...
    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]: ...
    def current_player(self, state: dict[str, Any]) -> str | None: ...
    def winner(self, state: dict[str, Any]) -> str | None: ...
    def is_terminal(self, state: dict[str, Any]) -> bool: ...
    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]: ...

    # Cursor model — lets MatchScreen stay game-agnostic.
    def initial_cursor(self) -> dict[str, Any]: ...
    def move_cursor(
        self, cursor: dict[str, Any], dr: int, dc: int
    ) -> dict[str, Any]: ...
    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]: ...

    # Optional animation hook. Return None when no animation is needed.
    def animation_for(
        self,
        prev_state: dict[str, Any],
        new_state: dict[str, Any],
    ) -> dict[str, Any] | None: ...

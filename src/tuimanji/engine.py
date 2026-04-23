"""Core protocol and exceptions for game implementations.

Games live in :mod:`tuimanji.games` and implement the :class:`Game` protocol —
a bundle of pure functions over ``state`` dicts. The store layer
(:mod:`tuimanji.store`) is the *only* place that touches the database; games
never do I/O, which is what keeps them trivially unit-testable and what makes
replay, spectators, and crash-resume fall out for free.

Exceptions raised by :meth:`Game.apply_action` (:class:`IllegalAction`,
:class:`NotYourTurn`) propagate out of :func:`tuimanji.store.submit_action`
and are surfaced by the UI layer — games should raise them freely rather
than return error sentinels.
"""

from typing import Any, Protocol, runtime_checkable

from rich.segment import Segment  # noqa: F401  (used by Game impls)
from textual.geometry import Size
from textual.strip import Strip


class GameError(Exception):
    """Base class for all game-layer errors."""


class IllegalAction(GameError):
    """Raised by :meth:`Game.apply_action` for malformed or illegal moves.

    The message should be specific enough for the UI to display to the
    offending player (e.g. ``"cell (1,2) is taken"``, ``"king would be in
    check"``).
    """


class NotYourTurn(GameError):
    """Raised when a player submits an action out of turn.

    This is surfaced from :func:`tuimanji.store.submit_action` in two
    situations: the straightforward stale-read case (``latest.current !=
    player``) and the race where two submissions for the same turn both pass
    the current-player check and the ``(match_id, turn)`` unique constraint
    trips at commit time.
    """

    def __init__(self, player: str, expected: str | None):
        super().__init__(f"not {player}'s turn (expected {expected})")
        self.player = player
        self.expected = expected


class MatchNotFound(GameError):
    """Raised when a match id does not resolve to any row in ``match``."""


class Animation(Protocol):
    """A frame-based visual transition between two states.

    Returned from :meth:`Game.animation_for` when a state diff warrants a
    pre-swap animation (e.g. a Connect 4 piece falling, a Reversi flip
    cascade, Royal Game of Ur dice rolling). The :class:`MatchScreen` keeps
    the canvas on ``prev_state`` while it drives ``frames`` ticks at
    ``interval`` seconds, pushing each ``overlay(frame)`` dict through
    ``canvas.set_ui(...)``, then swaps to ``new_state`` when done.
    """

    interval: float
    frames: int

    def overlay(self, frame: int) -> dict[str, Any]:
        """Return the UI overlay dict for the given frame index (0-based)."""
        ...


@runtime_checkable
class Game(Protocol):
    """The contract every game implements.

    All methods are pure: no I/O, no DB access, no clocks. A game is one
    module under ``src/tuimanji/games/`` plus an entry in
    :data:`tuimanji.games.REGISTRY`.

    ``state`` is always a JSON-serializable dict — it round-trips through
    the ``match_state`` SQLite column. Avoid custom classes, sets, tuples,
    or anything else that won't survive ``json.loads(json.dumps(state))``.

    Attributes:
        id: Stable slug used in the database and URLs. Never rename once
            matches exist.
        name: Human-readable name shown in the lobby.
        min_players: Minimum seats required to start a match.
        max_players: Maximum seats a match can hold.
    """

    id: str
    name: str
    min_players: int
    max_players: int

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        """Return the turn-0 state for a match seated with ``players``.

        ``players`` is ordered by seat index. Raise :class:`ValueError` if
        the count falls outside ``[min_players, max_players]``.
        """
        ...

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        """Return the next state after ``player`` submits ``action``.

        Must not mutate ``state``. Raise :class:`IllegalAction` for
        malformed or rule-violating input. The caller (the store) has
        already verified ``player == current_player(state)`` when this is
        called, but games may still validate defensively.
        """
        ...

    def current_player(self, state: dict[str, Any]) -> str | None:
        """Return the player expected to act next, or ``None`` at terminal."""
        ...

    def winner(self, state: dict[str, Any]) -> str | None:
        """Return the winning player id, or ``None`` for draw or in-progress."""
        ...

    def is_terminal(self, state: dict[str, Any]) -> bool:
        """Return ``True`` when the match is over (win, draw, or stalemate)."""
        ...

    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]:
        """Build the list of :class:`textual.strip.Strip` rows for the canvas.

        ``ui`` carries render-only state pushed by :class:`MatchScreen`:
        typically ``cursor``, ``active``, ``theme``, and ``viewer`` (for
        hidden-information games like Battleship / Crazy Eights). Games
        read colors from ``ui["theme"]`` via :mod:`tuimanji.ui.theme`,
        not hardcoded :class:`rich.style.Style` literals — keep ``render``
        testable without a running :class:`textual.app.App`.
        """
        ...

    # Cursor model — lets MatchScreen stay game-agnostic.
    def initial_cursor(self) -> dict[str, Any]:
        """Return the opaque starting cursor dict for a new MatchScreen."""
        ...

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        """Return the cursor after an arrow-key nudge by (``dr``, ``dc``).

        Games own wrapping and clamping. TicTacToe wraps on both axes;
        Connect 4 wraps only on col and ignores vertical arrows.
        """
        ...

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        """Translate a cursor into the action dict submitted on <enter>."""
        ...

    # Optional animation hook. Return None when no animation is needed.
    def animation_for(
        self,
        prev_state: dict[str, Any],
        new_state: dict[str, Any],
    ) -> Animation | None:
        """Return an :class:`Animation` for the state diff, or ``None``."""
        ...

"""Tuimanji — pubnix-local turn-based multiplayer TUI.

There is intentionally no server process: clients on the same machine share
state via a single SQLite WAL database at ``$TUIMANJI_DB/tuimanji.db``.

The :class:`Game` protocol is the extension point — implement
``initial_state``, ``apply_action``, ``current_player``, ``winner``,
``is_terminal``, ``render``, and the cursor trio, then register the class in
:data:`tuimanji.games.REGISTRY`. All game logic is pure: no I/O, no DB,
trivially unit-testable.

The store layer (:mod:`tuimanji.store`) is the only thing that touches the
database, and :class:`models.MatchState` / :class:`models.Action` rows are
append-only — turn N is an insert, never an update — which is what gives
replay, spectators, and crash-resume for free.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

from .engine import (
    Animation,
    Game,
    GameError,
    IllegalAction,
    MatchNotFound,
    NotYourTurn,
)
from .games import REGISTRY, all_games, get

try:
    # Single source of truth: pyproject.toml. bumpversion already updates
    # that file, so the CLI's --version follows automatically.
    __version__ = _pkg_version("tuimanji")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "Animation",
    "Game",
    "GameError",
    "IllegalAction",
    "MatchNotFound",
    "NotYourTurn",
    "REGISTRY",
    "__version__",
    "all_games",
    "get",
    "main",
]


def main() -> None:
    """Console-script entry point — defers to :func:`tuimanji.cli.main`."""
    from .cli import main as _main

    _main()

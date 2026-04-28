"""The game registry.

To add a new game:

1. Create ``src/tuimanji/games/your_game.py`` with a class implementing
   :class:`tuimanji.engine.Game`. Keep it pure — no I/O.
2. Import and register it in :data:`REGISTRY` below, keyed by ``id``.
3. Add ``tests/test_your_game.py`` — pure state transitions unit-test
   trivially against the ``state`` dict.

See ``docs/adding-a-game.md`` for a worked example and
:mod:`tuimanji.games.peg_solitaire` for the minimal single-player shape.
"""

from ..engine import Game
from .battleship import Battleship
from .checkers import Checkers
from .chess import Chess
from .connect4 import Connect4
from .crazy_eights import CrazyEights
from .mastermind import Mastermind
from .peg_solitaire import PegSolitaire
from .reversi import Reversi
from .royal_ur import RoyalUr
from .tic_tac_toe import TicTacToe

REGISTRY: dict[str, Game] = {
    TicTacToe.id: TicTacToe(),
    Connect4.id: Connect4(),
    Battleship.id: Battleship(),
    Reversi.id: Reversi(),
    Chess.id: Chess(),
    Checkers.id: Checkers(),
    PegSolitaire.id: PegSolitaire(),
    CrazyEights.id: CrazyEights(),
    RoyalUr.id: RoyalUr(),
    Mastermind.id: Mastermind(),
}


def get(game_id: str) -> Game:
    """Return the registered :class:`Game` singleton for ``game_id``.

    Raises :class:`KeyError` for unknown ids.
    """
    return REGISTRY[game_id]


def all_games() -> list[Game]:
    """Return every registered :class:`Game`, in registry order."""
    return list(REGISTRY.values())

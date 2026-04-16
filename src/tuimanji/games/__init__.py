from ..engine import Game
from .battleship import Battleship
from .checkers import Checkers
from .chess import Chess
from .connect4 import Connect4
from .crazy_eights import CrazyEights
from .peg_solitaire import PegSolitaire
from .reversi import Reversi
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
}


def get(game_id: str) -> Game:
    return REGISTRY[game_id]


def all_games() -> list[Game]:
    return list(REGISTRY.values())

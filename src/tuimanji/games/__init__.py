from ..engine import Game
from .battleship import Battleship
from .chess import Chess
from .connect4 import Connect4
from .peg_solitaire import PegSolitaire
from .reversi import Reversi
from .tic_tac_toe import TicTacToe

REGISTRY: dict[str, Game] = {
    TicTacToe.id: TicTacToe(),
    Connect4.id: Connect4(),
    Battleship.id: Battleship(),
    Reversi.id: Reversi(),
    Chess.id: Chess(),
    PegSolitaire.id: PegSolitaire(),
}


def get(game_id: str) -> Game:
    return REGISTRY[game_id]


def all_games() -> list[Game]:
    return list(REGISTRY.values())

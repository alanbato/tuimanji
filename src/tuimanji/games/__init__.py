from ..engine import Game
from .connect4 import Connect4
from .tic_tac_toe import TicTacToe

REGISTRY: dict[str, Game] = {
    TicTacToe.id: TicTacToe(),
    Connect4.id: Connect4(),
}


def get(game_id: str) -> Game:
    return REGISTRY[game_id]


def all_games() -> list[Game]:
    return list(REGISTRY.values())

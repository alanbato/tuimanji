from ..engine import Game
from .tic_tac_toe import TicTacToe

REGISTRY: dict[str, Game] = {
    TicTacToe.id: TicTacToe(),
}


def get(game_id: str) -> Game:
    return REGISTRY[game_id]


def all_games() -> list[Game]:
    return list(REGISTRY.values())

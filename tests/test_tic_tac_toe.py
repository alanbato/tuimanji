import pytest

from tuimanji.engine import IllegalAction
from tuimanji.games.tic_tac_toe import TicTacToe


@pytest.fixture
def game() -> TicTacToe:
    return TicTacToe()


def test_initial_state(game: TicTacToe):
    state = game.initial_state(["alice", "bob"])
    assert state["turn_player"] == "alice"
    assert state["marks"] == {"alice": "X", "bob": "O"}
    assert state["winner"] is None
    assert all(cell == "." for row in state["board"] for cell in row)


def test_alternating_turns(game: TicTacToe):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"row": 0, "col": 0})
    assert s["turn_player"] == "bob"
    s = game.apply_action(s, "bob", {"row": 1, "col": 1})
    assert s["turn_player"] == "alice"


def test_wrong_turn_rejected(game: TicTacToe):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "bob", {"row": 0, "col": 0})


def test_taken_cell_rejected(game: TicTacToe):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"row": 0, "col": 0})
    with pytest.raises(IllegalAction):
        game.apply_action(s, "bob", {"row": 0, "col": 0})


def test_out_of_bounds_rejected(game: TicTacToe):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"row": 5, "col": 0})


@pytest.mark.parametrize(
    "moves,winner",
    [
        # Row win
        ([(0, 0), (1, 0), (0, 1), (1, 1), (0, 2)], "alice"),
        # Column win
        ([(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)], "alice"),
        # Diagonal win
        ([(0, 0), (0, 1), (1, 1), (0, 2), (2, 2)], "alice"),
        # Bob wins anti-diagonal
        ([(0, 0), (0, 2), (1, 0), (1, 1), (2, 1), (2, 0)], "bob"),
    ],
)
def test_win_detection(game: TicTacToe, moves, winner):
    s = game.initial_state(["alice", "bob"])
    players = ["alice", "bob"]
    for i, (r, c) in enumerate(moves):
        s = game.apply_action(s, players[i % 2], {"row": r, "col": c})
    assert s["winner"] == winner
    assert game.is_terminal(s)
    assert game.current_player(s) is None


def test_draw(game: TicTacToe):
    s = game.initial_state(["alice", "bob"])
    moves = [
        ("alice", 0, 0),
        ("bob", 0, 1),
        ("alice", 0, 2),
        ("bob", 1, 1),
        ("alice", 1, 0),
        ("bob", 1, 2),
        ("alice", 2, 1),
        ("bob", 2, 0),
        ("alice", 2, 2),
    ]
    for p, r, c in moves:
        s = game.apply_action(s, p, {"row": r, "col": c})
    assert s["winner"] is None
    assert game.is_terminal(s)


def test_no_moves_after_terminal(game: TicTacToe):
    s = game.initial_state(["alice", "bob"])
    for p, r, c in [
        ("alice", 0, 0),
        ("bob", 1, 0),
        ("alice", 0, 1),
        ("bob", 1, 1),
        ("alice", 0, 2),
    ]:
        s = game.apply_action(s, p, {"row": r, "col": c})
    assert s["winner"] == "alice"
    with pytest.raises(IllegalAction):
        game.apply_action(s, "bob", {"row": 2, "col": 2})

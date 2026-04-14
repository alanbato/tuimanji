import pytest

from tuimanji.engine import IllegalAction
from tuimanji.games.connect4 import COLS, ROWS, Connect4, FallAnimation


@pytest.fixture
def game() -> Connect4:
    return Connect4()


def test_initial_state(game: Connect4):
    state = game.initial_state(["alice", "bob"])
    assert state["turn_player"] == "alice"
    assert state["marks"] == {"alice": "R", "bob": "Y"}
    assert state["winner"] is None
    assert state["last_drop"] is None
    assert all(cell == "." for row in state["board"] for cell in row)


def test_drop_lands_at_bottom(game: Connect4):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"col": 3})
    assert s["board"][ROWS - 1][3] == "R"
    assert s["last_drop"] == [ROWS - 1, 3]
    assert s["turn_player"] == "bob"


def test_stack_on_top(game: Connect4):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"col": 0})
    s = game.apply_action(s, "bob", {"col": 0})
    assert s["board"][ROWS - 1][0] == "R"
    assert s["board"][ROWS - 2][0] == "Y"


def test_full_column_rejected(game: Connect4):
    s = game.initial_state(["alice", "bob"])
    players = ["alice", "bob"]
    for i in range(ROWS):
        s = game.apply_action(s, players[i % 2], {"col": 0})
    with pytest.raises(IllegalAction, match="full"):
        s = game.apply_action(s, players[ROWS % 2], {"col": 0})


def test_out_of_bounds(game: Connect4):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"col": COLS})


def test_wrong_turn(game: Connect4):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "bob", {"col": 0})


def _play(game: Connect4, moves: list[tuple[str, int]]) -> dict:
    s = game.initial_state(["alice", "bob"])
    for p, col in moves:
        s = game.apply_action(s, p, {"col": col})
    return s


def test_horizontal_win(game: Connect4):
    moves = [
        ("alice", 0),
        ("bob", 0),
        ("alice", 1),
        ("bob", 1),
        ("alice", 2),
        ("bob", 2),
        ("alice", 3),
    ]
    s = _play(game, moves)
    assert s["winner"] == "alice"
    assert game.is_terminal(s)


def test_vertical_win(game: Connect4):
    moves = [
        ("alice", 0),
        ("bob", 1),
        ("alice", 0),
        ("bob", 1),
        ("alice", 0),
        ("bob", 1),
        ("alice", 0),
    ]
    s = _play(game, moves)
    assert s["winner"] == "alice"


def test_diagonal_win(game: Connect4):
    # Build a bottom-left to top-right diagonal for alice.
    moves = [
        ("alice", 0),
        ("bob", 1),
        ("alice", 1),
        ("bob", 2),
        ("alice", 2),
        ("bob", 3),
        ("alice", 2),
        ("bob", 3),
        ("alice", 3),
        ("bob", 6),
        ("alice", 3),
    ]
    s = _play(game, moves)
    assert s["winner"] == "alice"


def test_cursor_wraps_columns(game: Connect4):
    cur = game.initial_cursor()
    assert cur["col"] == 0
    cur = game.move_cursor(cur, 0, -1)
    assert cur["col"] == COLS - 1
    cur = game.move_cursor(cur, 0, 1)
    assert cur["col"] == 0


def test_cursor_action(game: Connect4):
    cur = {"row": 0, "col": 4}
    assert game.cursor_action(cur) == {"col": 4}


def test_animation_for_drop(game: Connect4):
    s0 = game.initial_state(["alice", "bob"])
    s1 = game.apply_action(s0, "alice", {"col": 2})
    anim = game.animation_for(s0, s1)
    assert isinstance(anim, FallAnimation)
    assert anim.col == 2
    assert anim.target_row == ROWS - 1
    assert anim.mark == "R"
    assert anim.frames == ROWS
    assert anim.overlay(0) == {"kind": "fall", "col": 2, "row": 0, "mark": "R"}


def test_animation_none_when_no_change(game: Connect4):
    s = game.initial_state(["alice", "bob"])
    assert game.animation_for(s, s) is None

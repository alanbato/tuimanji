from typing import cast

import pytest

from tuimanji.engine import IllegalAction
from tuimanji.games.reversi import COLS, ROWS, Reversi, _legal_moves


@pytest.fixture
def game() -> Reversi:
    return Reversi()


def test_initial_state(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    assert s["turn_player"] == "alice"
    assert s["marks"] == {"alice": "B", "bob": "W"}
    assert s["winner"] is None
    assert s["last_flip"] is None
    assert s["last_pass"] is None
    assert s["board"][3][3] == "W"
    assert s["board"][4][4] == "W"
    assert s["board"][3][4] == "B"
    assert s["board"][4][3] == "B"


def test_initial_legal_moves_are_four(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    moves = _legal_moves(s["board"], "B")
    assert set(moves.keys()) == {(2, 3), (3, 2), (4, 5), (5, 4)}


def test_place_captures_and_flips(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"row": 2, "col": 3})
    assert s["board"][2][3] == "B"
    assert s["board"][3][3] == "B"  # flipped from W
    assert s["turn_player"] == "bob"
    assert s["last_flip"]["cells"] == [[3, 3]]
    assert s["last_flip"]["to"] == "B"


def test_illegal_no_capture(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="no captures"):
        game.apply_action(s, "alice", {"row": 0, "col": 0})


def test_cell_taken(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="taken"):
        game.apply_action(s, "alice", {"row": 3, "col": 3})


def test_out_of_bounds(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="out of bounds"):
        game.apply_action(s, "alice", {"row": ROWS, "col": 0})


def test_wrong_turn(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="not bob"):
        game.apply_action(s, "bob", {"row": 2, "col": 3})


def test_cursor_wraps(game: Reversi):
    cur = game.initial_cursor()
    cur = game.move_cursor(cur, -4, 0)
    assert cur["row"] == (3 - 4) % ROWS
    cur = game.move_cursor(cur, 0, COLS)
    assert cur["col"] == 3


def test_cursor_action(game: Reversi):
    assert game.cursor_action({"row": 2, "col": 5}) == {"row": 2, "col": 5}


def test_animation_for_flip(game: Reversi):
    s0 = game.initial_state(["alice", "bob"])
    s1 = game.apply_action(s0, "alice", {"row": 2, "col": 3})
    anim = game.animation_for(s0, s1)
    assert anim is not None
    assert anim["type"] == "flip"
    assert anim["cells"] == [[3, 3]]
    assert anim["to"] == "B"
    assert anim["at"] == [2, 3]


def test_animation_none_without_flip(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    assert game.animation_for(s, s) is None


def test_pass_when_opponent_has_no_moves(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    # Diagonal line of B/W discs: after black plays (2,2) it captures
    # (1,1) and (3,3), leaving a single W at (5,5). White can only reach
    # that W along the main diagonal, which is fully blocked by B discs,
    # so white has no legal reply — but black can still capture from (6,6).
    board = [["." for _ in range(COLS)] for _ in range(ROWS)]
    board[0][0] = "B"
    board[1][1] = "W"
    board[3][3] = "W"
    board[4][4] = "B"
    board[5][5] = "W"
    s = {**s, "board": board}
    s = game.apply_action(s, "alice", {"row": 2, "col": 2})
    assert s["board"][1][1] == "B"
    assert s["board"][3][3] == "B"
    assert s["board"][5][5] == "W"
    assert s["turn_player"] == "alice"
    assert s["last_pass"] == "bob"
    assert not game.is_terminal(s)


def test_winner_by_count_on_full_board(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    board = [["B" for _ in range(COLS)] for _ in range(ROWS)]
    for c in range(COLS):
        board[0][c] = "W"
    s = {**s, "board": board}
    assert game.is_terminal(s)
    marks = cast(dict[str, str], s["marks"])
    assert game._winner_by_count(board, marks) == "alice"


def test_terminal_when_neither_can_move(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    board = [["B" for _ in range(COLS)] for _ in range(ROWS)]
    s = {**s, "board": board}
    assert game.is_terminal(s)
    assert game.current_player(s) is None


def test_render_returns_strips_without_theme(game: Reversi):
    s = game.initial_state(["alice", "bob"])
    from textual.geometry import Size

    lines = game.render(s, Size(40, 30), ui={"cursor": {"row": 2, "col": 3}})
    assert len(lines) > 0

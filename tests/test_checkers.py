from typing import Any

import pytest

from tuimanji.engine import IllegalAction
from tuimanji.games.checkers import (
    EMPTY_CELL,
    RED,
    RED_KING,
    SIZE,
    WHITE,
    WHITE_KING,
    Checkers,
    _any_jumps_for_color,
    _initial_board,
    _piece_jumps,
)


@pytest.fixture
def game() -> Checkers:
    return Checkers()


def _empty() -> list[list[str]]:
    return [[EMPTY_CELL] * SIZE for _ in range(SIZE)]


def _state(
    board: list[list[str]],
    turn: str = "alice",
    continue_from: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "board": board,
        "marks": {"alice": RED, "bob": WHITE},
        "order": ["alice", "bob"],
        "turn_player": turn,
        "winner": None,
        "continue_from": continue_from,
        "last_move": None,
    }


def test_initial_layout(game: Checkers):
    s = game.initial_state(["alice", "bob"])
    assert s["turn_player"] == "alice"
    assert s["marks"] == {"alice": RED, "bob": WHITE}
    assert s["continue_from"] is None
    board = s["board"]
    reds = sum(1 for row in board for p in row if p == RED)
    whites = sum(1 for row in board for p in row if p == WHITE)
    assert reds == 12
    assert whites == 12
    # White fills dark squares on top three rows.
    assert board[0][1] == WHITE
    assert board[2][7] == WHITE
    # Red fills dark squares on bottom three rows.
    assert board[5][0] == RED
    assert board[7][6] == RED


def test_simple_forward_step(game: Checkers):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"type": "move", "from": [5, 0], "to": [4, 1]})
    assert s["board"][5][0] == EMPTY_CELL
    assert s["board"][4][1] == RED
    assert s["turn_player"] == "bob"
    assert s["continue_from"] is None


def test_backward_step_rejected_for_man(game: Checkers):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="illegal step"):
        game.apply_action(s, "alice", {"type": "move", "from": [5, 0], "to": [6, 1]})


def test_forced_capture_blocks_simple_move(game: Checkers):
    board = _empty()
    board[5][2] = RED
    board[4][3] = WHITE
    s = _state(board)
    with pytest.raises(IllegalAction, match="must capture"):
        game.apply_action(s, "alice", {"type": "move", "from": [5, 2], "to": [4, 1]})


def test_capture_removes_victim(game: Checkers):
    board = _empty()
    board[5][2] = RED
    board[4][3] = WHITE
    s = _state(board)
    s = game.apply_action(s, "alice", {"type": "move", "from": [5, 2], "to": [3, 4]})
    assert s["board"][5][2] == EMPTY_CELL
    assert s["board"][4][3] == EMPTY_CELL
    assert s["board"][3][4] == RED
    assert s["turn_player"] == "bob"
    assert s["last_move"]["captured"] == [4, 3]


def test_multi_jump_continuation(game: Checkers):
    board = _empty()
    board[6][1] = RED
    board[5][2] = WHITE
    board[3][2] = WHITE
    board[7][0] = RED  # spare piece we'll try to move mid-jump
    s = _state(board)
    s = game.apply_action(s, "alice", {"type": "move", "from": [6, 1], "to": [4, 3]})
    assert s["turn_player"] == "alice"
    assert s["continue_from"] == [4, 3]
    assert s["board"][5][2] == EMPTY_CELL
    assert s["board"][4][3] == RED
    # Second jump must continue from the same square.
    with pytest.raises(IllegalAction, match="must continue"):
        game.apply_action(s, "alice", {"type": "move", "from": [7, 0], "to": [6, 1]})
    # Restore the spare piece for the continuation jump.
    s = game.apply_action(s, "alice", {"type": "move", "from": [4, 3], "to": [2, 1]})
    assert s["board"][3][2] == EMPTY_CELL
    assert s["board"][2][1] == RED
    assert s["turn_player"] == "bob"
    assert s["continue_from"] is None


def test_promotion_ends_turn_even_with_more_jumps(game: Checkers):
    # Red man at (2,1) jumps white at (1,2) landing at (0,3) — king row.
    # Another white at (1,4) would allow a continuing jump to (2,5) if not promoted,
    # but promotion must end the turn.
    board = _empty()
    board[2][1] = RED
    board[1][2] = WHITE
    board[1][4] = WHITE
    s = _state(board)
    s = game.apply_action(s, "alice", {"type": "move", "from": [2, 1], "to": [0, 3]})
    assert s["board"][0][3] == RED_KING
    assert s["continue_from"] is None
    assert s["turn_player"] == "bob"
    assert s["last_move"]["promoted"] is True
    # White piece at (1,4) is untouched.
    assert s["board"][1][4] == WHITE


def test_king_moves_backward(game: Checkers):
    board = _empty()
    board[4][3] = RED_KING
    s = _state(board)
    s = game.apply_action(s, "alice", {"type": "move", "from": [4, 3], "to": [5, 4]})
    assert s["board"][5][4] == RED_KING
    assert s["board"][4][3] == EMPTY_CELL


def test_win_by_no_pieces(game: Checkers):
    board = _empty()
    board[5][2] = RED
    board[4][3] = WHITE
    s = _state(board)
    s = game.apply_action(s, "alice", {"type": "move", "from": [5, 2], "to": [3, 4]})
    assert s["winner"] == "alice"
    assert game.is_terminal(s) is True


def test_win_by_no_legal_moves(game: Checkers):
    # White cornered with no moves: (0,7) surrounded impossibly. Place white at
    # (0,1) with a red wall so white has no steps and no jumps.
    board = _empty()
    board[0][1] = WHITE
    board[1][0] = RED
    board[1][2] = RED
    board[2][3] = RED  # blocks white's would-be capture landing
    # Give red a throwaway square to move so red's action isn't forced capture.
    board[6][1] = RED
    s = _state(board)
    s = game.apply_action(s, "alice", {"type": "move", "from": [6, 1], "to": [5, 0]})
    assert s["winner"] == "alice"


def test_not_your_turn(game: Checkers):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="not bob's turn"):
        game.apply_action(s, "bob", {"type": "move", "from": [2, 1], "to": [3, 0]})


def test_white_man_moves_downward(game: Checkers):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"type": "move", "from": [5, 0], "to": [4, 1]})
    s = game.apply_action(s, "bob", {"type": "move", "from": [2, 1], "to": [3, 0]})
    assert s["board"][3][0] == WHITE
    assert s["turn_player"] == "alice"


def test_any_jumps_helper_detects_king_backjump(game: Checkers):
    board = _empty()
    board[3][3] = WHITE_KING
    board[4][4] = RED
    assert _any_jumps_for_color(board, WHITE) is True
    jumps = _piece_jumps(board, 3, 3)
    assert (5, 5, 4, 4) in jumps


def test_initial_board_helper_matches_state(game: Checkers):
    assert _initial_board() == game.initial_state(["a", "b"])["board"]


def test_cursor_moves_diagonally(game: Checkers):
    cur = game.init_cursor_for("alice", game.initial_state(["alice", "bob"]))
    assert (cur["row"] + cur["col"]) % 2 == 1
    # Each cardinal arrow maps to a diagonal; every destination stays dark
    # and is exactly one step away on both axes (modulo wrap).
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nxt = game.move_cursor(cur, dr, dc)
        assert (nxt["row"] + nxt["col"]) % 2 == 1
        row_delta = (nxt["row"] - cur["row"]) % SIZE
        col_delta = (nxt["col"] - cur["col"]) % SIZE
        assert row_delta in (1, SIZE - 1)
        assert col_delta in (1, SIZE - 1)


def test_stage_and_cursor_action(game: Checkers):
    cur = game.initial_cursor()
    cur = {**cur, "row": 5, "col": 0}
    staged = game.stage_cursor(cur)
    assert staged["mode"] == "target"
    assert staged["from"] == [5, 0]
    staged = {**staged, "row": 4, "col": 1}
    action = game.cursor_action(staged)
    assert action == {"type": "move", "from": [5, 0], "to": [4, 1]}


def test_sync_cursor_snaps_to_continue_from(game: Checkers):
    board = _empty()
    board[4][3] = RED
    s = _state(board, continue_from=[4, 3])
    cur = {"mode": "target", "row": 6, "col": 1, "from": [6, 1], "viewer_seat": 0}
    synced = game.sync_cursor(cur, s)
    assert synced["mode"] == "select"
    assert (synced["row"], synced["col"]) == (4, 3)
    assert synced["from"] is None

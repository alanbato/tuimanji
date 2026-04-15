from typing import Any

import pytest
from textual.geometry import Size

from tuimanji.engine import IllegalAction
from tuimanji.games.peg_solitaire import (
    EMPTY,
    PEG,
    SIZE,
    VOID,
    PegSolitaire,
    _empty_cross,
    _is_void,
    _peg_count,
)


@pytest.fixture
def game() -> PegSolitaire:
    return PegSolitaire()


def _state(
    board: list[list[str]], player: str = "alice", moves: int = 0
) -> dict[str, Any]:
    return {
        "board": board,
        "order": [player],
        "turn_player": player,
        "winner": None,
        "moves": moves,
        "last_move": None,
    }


def _blank() -> list[list[str]]:
    return [
        [VOID if _is_void(r, c) else EMPTY for c in range(SIZE)] for r in range(SIZE)
    ]


def test_initial_state(game: PegSolitaire):
    s = game.initial_state(["alice"])
    assert s["turn_player"] == "alice"
    assert s["board"][3][3] == EMPTY
    assert _peg_count(s["board"]) == 32
    assert s["winner"] is None
    assert not game.is_terminal(s)
    assert game.current_player(s) == "alice"


def test_requires_exactly_one_player(game: PegSolitaire):
    with pytest.raises(ValueError):
        game.initial_state(["alice", "bob"])


def test_valid_first_jump(game: PegSolitaire):
    s = game.initial_state(["alice"])
    s2 = game.apply_action(s, "alice", {"from": [5, 3], "to": [3, 3]})
    assert s2["board"][5][3] == EMPTY
    assert s2["board"][4][3] == EMPTY
    assert s2["board"][3][3] == PEG
    assert s2["moves"] == 1
    assert _peg_count(s2["board"]) == 31
    assert s2["last_move"] == {"from": [5, 3], "over": [4, 3], "to": [3, 3]}


def test_reject_non_two_square_jump(game: PegSolitaire):
    s = game.initial_state(["alice"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"from": [5, 3], "to": [4, 3]})


def test_reject_diagonal(game: PegSolitaire):
    s = game.initial_state(["alice"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"from": [5, 3], "to": [3, 1]})


def test_reject_jump_over_empty(game: PegSolitaire):
    b = _blank()
    b[3][1] = PEG
    # (3,3) is empty, (3,2) is also empty → cannot jump over empty.
    s = _state(b)
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"from": [3, 1], "to": [3, 3]})


def test_reject_source_not_peg(game: PegSolitaire):
    s = game.initial_state(["alice"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"from": [3, 3], "to": [5, 3]})


def test_reject_destination_not_empty(game: PegSolitaire):
    s = game.initial_state(["alice"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"from": [5, 3], "to": [5, 5]})


def test_reject_void_coordinates(game: PegSolitaire):
    s = game.initial_state(["alice"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"from": [0, 0], "to": [0, 2]})


def test_win_when_one_peg_remains(game: PegSolitaire):
    b = _blank()
    b[3][1] = PEG
    b[3][2] = PEG
    s = _state(b)
    s2 = game.apply_action(s, "alice", {"from": [3, 1], "to": [3, 3]})
    assert _peg_count(s2["board"]) == 1
    assert s2["board"][3][3] == PEG
    assert s2["winner"] == "alice"
    assert game.is_terminal(s2)
    assert game.current_player(s2) is None


def test_stuck_terminal_without_winner(game: PegSolitaire):
    b = _blank()
    b[3][2] = PEG
    b[5][4] = PEG
    s = _state(b)
    assert game.is_terminal(s)
    assert game.winner(s) is None
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"from": [3, 2], "to": [3, 0]})


def test_cursor_move_wraps(game: PegSolitaire):
    c = game.initial_cursor()
    c = game.move_cursor(c, -6, 0)
    assert c["row"] == (5 - 6) % SIZE
    c = game.move_cursor(c, 0, 7)
    assert c["col"] == c["col"] % SIZE


def test_prepare_action_transitions_select_to_target(game: PegSolitaire):
    s = game.initial_state(["alice"])
    c = game.initial_cursor()
    new_c = game.prepare_action(c, s)
    assert new_c is not None
    assert new_c["mode"] == "target"
    assert new_c["from"] == [5, 3]


def test_prepare_action_rejects_void(game: PegSolitaire):
    s = game.initial_state(["alice"])
    c = {**game.initial_cursor(), "row": 0, "col": 0}
    with pytest.raises(IllegalAction):
        game.prepare_action(c, s)


def test_prepare_action_rejects_empty_cell(game: PegSolitaire):
    s = game.initial_state(["alice"])
    c = {**game.initial_cursor(), "row": 3, "col": 3}
    with pytest.raises(IllegalAction):
        game.prepare_action(c, s)


def test_prepare_action_passthrough_in_target_mode(game: PegSolitaire):
    s = game.initial_state(["alice"])
    c = {"row": 3, "col": 3, "mode": "target", "from": [5, 3]}
    assert game.prepare_action(c, s) is None


def test_cursor_action_in_target_mode(game: PegSolitaire):
    c = {"row": 3, "col": 3, "mode": "target", "from": [5, 3]}
    assert game.cursor_action(c) == {"from": [5, 3], "to": [3, 3]}


def test_cursor_action_in_select_mode_rejected(game: PegSolitaire):
    c = game.initial_cursor()
    with pytest.raises(IllegalAction):
        game.cursor_action(c)


def test_stage_cursor_cancels_selection(game: PegSolitaire):
    c = {"row": 2, "col": 3, "mode": "target", "from": [5, 3]}
    c2 = game.stage_cursor(c)
    assert c2["mode"] == "select"
    assert c2["from"] is None
    assert (c2["row"], c2["col"]) == (5, 3)


def test_sync_cursor_clears_stale_selection(game: PegSolitaire):
    b = _empty_cross()
    # Remove the peg at (5,3) so a lingering target-mode selection is stale.
    b[5][3] = EMPTY
    s = _state(b)
    c = {"row": 2, "col": 3, "mode": "target", "from": [5, 3]}
    c2 = game.sync_cursor(c, s)
    assert c2["mode"] == "select"
    assert c2["from"] is None


def test_render_returns_strips(game: PegSolitaire):
    s = game.initial_state(["alice"])
    strips = game.render(s, Size(40, 30), None)
    assert len(strips) > SIZE

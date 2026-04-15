from typing import Any

import pytest

from tuimanji.engine import IllegalAction
from tuimanji.games.chess import (
    BLACK,
    EMPTY_CELL,
    SIZE,
    WHITE,
    Chess,
    _in_check,
    _legal_destinations,
    _pseudo_moves,
)


@pytest.fixture
def game() -> Chess:
    return Chess()


@pytest.fixture
def fresh(game: Chess) -> dict[str, Any]:
    return game.initial_state(["alice", "bob"])


def _empty_board() -> list[list[str]]:
    return [[EMPTY_CELL] * SIZE for _ in range(SIZE)]


def _state_with_board(
    board: list[list[str]],
    turn: str = "alice",
    castling: dict[str, dict[str, bool]] | None = None,
    en_passant: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "board": board,
        "marks": {"alice": WHITE, "bob": BLACK},
        "order": ["alice", "bob"],
        "turn_player": turn,
        "winner": None,
        "castling": castling
        or {WHITE: {"K": False, "Q": False}, BLACK: {"K": False, "Q": False}},
        "en_passant": en_passant,
        "halfmove": 0,
        "fullmove": 1,
        "last_move": None,
        "in_check": None,
        "result": None,
    }


def _move(
    game: Chess,
    state: dict[str, Any],
    player: str,
    fr: tuple[int, int],
    to: tuple[int, int],
    promote: str | None = None,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "type": "move",
        "from": list(fr),
        "to": list(to),
    }
    if promote is not None:
        action["promote"] = promote
    return game.apply_action(state, player, action)


def test_initial_state(game: Chess, fresh: dict[str, Any]):
    assert fresh["turn_player"] == "alice"
    assert fresh["marks"] == {"alice": WHITE, "bob": BLACK}
    assert fresh["board"][7][4] == "wK"
    assert fresh["board"][0][4] == "bK"
    # 32 pieces on the board
    total = sum(1 for row in fresh["board"] for cell in row if cell)
    assert total == 32


def test_pawn_single_and_double_push(game: Chess, fresh: dict[str, Any]):
    s = _move(game, fresh, "alice", (6, 4), (4, 4))  # e2-e4
    assert s["board"][6][4] == ""
    assert s["board"][4][4] == "wP"
    assert s["en_passant"] == [5, 4]
    assert s["turn_player"] == "bob"
    # Bob cannot move a white pawn
    with pytest.raises(IllegalAction, match="turn|yours"):
        _move(game, s, "bob", (6, 0), (5, 0))


def test_pawn_blocked(game: Chess):
    b = _empty_board()
    b[6][4] = "wP"
    b[5][4] = "bP"
    s = _state_with_board(b)
    with pytest.raises(IllegalAction, match="illegal"):
        _move(game, s, "alice", (6, 4), (5, 4))
    # But it can capture diagonally
    b[5][5] = "bP"
    s = _state_with_board(b)
    s = _move(game, s, "alice", (6, 4), (5, 5))
    assert s["board"][5][5] == "wP"


def test_en_passant_capture(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[0][4] = "bK"
    b[3][4] = "wP"  # white pawn on e5
    b[1][5] = "bP"  # black pawn on f7
    s = _state_with_board(b, turn="bob")
    # black plays f7-f5, creating en passant target on f6
    s = _move(game, s, "bob", (1, 5), (3, 5))
    assert s["en_passant"] == [2, 5]
    # white plays exf6 en passant
    s = _move(game, s, "alice", (3, 4), (2, 5))
    assert s["board"][2][5] == "wP"
    assert s["board"][3][5] == ""  # captured pawn removed
    assert s["last_move"]["special"] == "enpassant"


def test_knight_moves(game: Chess, fresh: dict[str, Any]):
    # Nb1-c3 is legal from the initial position
    s = _move(game, fresh, "alice", (7, 1), (5, 2))
    assert s["board"][5][2] == "wN"


def test_castling_kingside(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[7][7] = "wR"
    b[0][4] = "bK"
    s = _state_with_board(
        b,
        castling={WHITE: {"K": True, "Q": True}, BLACK: {"K": False, "Q": False}},
    )
    s = _move(game, s, "alice", (7, 4), (7, 6))
    assert s["board"][7][6] == "wK"
    assert s["board"][7][5] == "wR"
    assert s["board"][7][7] == ""
    assert s["last_move"]["special"] == "castle_K"
    assert s["castling"][WHITE] == {"K": False, "Q": False}


def test_castling_queenside(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[7][0] = "wR"
    b[0][4] = "bK"
    s = _state_with_board(
        b,
        castling={WHITE: {"K": True, "Q": True}, BLACK: {"K": False, "Q": False}},
    )
    s = _move(game, s, "alice", (7, 4), (7, 2))
    assert s["board"][7][2] == "wK"
    assert s["board"][7][3] == "wR"
    assert s["last_move"]["special"] == "castle_Q"


def test_castling_blocked_by_piece(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[7][7] = "wR"
    b[7][5] = "wN"  # f1 occupied
    b[0][4] = "bK"
    s = _state_with_board(
        b,
        castling={WHITE: {"K": True, "Q": True}, BLACK: {"K": False, "Q": False}},
    )
    with pytest.raises(IllegalAction):
        _move(game, s, "alice", (7, 4), (7, 6))


def test_castling_through_check(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[7][7] = "wR"
    b[0][4] = "bK"
    b[0][5] = "bR"  # attacks f-file including f1
    s = _state_with_board(
        b,
        castling={WHITE: {"K": True, "Q": True}, BLACK: {"K": False, "Q": False}},
    )
    with pytest.raises(IllegalAction):
        _move(game, s, "alice", (7, 4), (7, 6))


def test_cannot_leave_king_in_check(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[7][3] = "wB"
    b[7][0] = "bR"  # pins bishop along the 1st rank
    b[0][4] = "bK"
    s = _state_with_board(b)
    with pytest.raises(IllegalAction):
        _move(game, s, "alice", (7, 3), (6, 4))


def test_fools_mate(game: Chess, fresh: dict[str, Any]):
    # f2-f3, e7-e5, g2-g4, Qd8-h4#
    s = _move(game, fresh, "alice", (6, 5), (5, 5))
    s = _move(game, s, "bob", (1, 4), (3, 4))
    s = _move(game, s, "alice", (6, 6), (4, 6))
    s = _move(game, s, "bob", (0, 3), (4, 7))
    assert s["winner"] == "bob"
    assert s["result"] == "checkmate"
    assert game.is_terminal(s)
    assert game.current_player(s) is None


def test_stalemate(game: Chess):
    b = _empty_board()
    b[0][0] = "bK"
    b[2][1] = "wK"
    b[2][2] = "wQ"
    s = _state_with_board(b, turn="alice")
    # Qc6-c7: black king has no moves, not in check → stalemate
    s = _move(game, s, "alice", (2, 2), (1, 2))
    assert s["result"] == "stalemate"
    assert s["winner"] == "draw"
    assert game.winner(s) is None
    assert game.is_terminal(s)


def test_promotion_required(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[0][4] = "bK"
    b[1][0] = "wP"  # about to promote
    s = _state_with_board(b)
    with pytest.raises(IllegalAction, match="promotion"):
        _move(game, s, "alice", (1, 0), (0, 0))
    s2 = _move(game, s, "alice", (1, 0), (0, 0), promote="Q")
    assert s2["board"][0][0] == "wQ"
    assert s2["last_move"]["promoted"] == "wQ"


def test_promotion_underpromotion(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[0][7] = "bK"
    b[1][0] = "wP"
    s = _state_with_board(b)
    s = _move(game, s, "alice", (1, 0), (0, 0), promote="N")
    assert s["board"][0][0] == "wN"


def test_cursor_transitions(game: Chess):
    cur = game.initial_cursor()
    assert cur["mode"] == "select"
    # Move to a pawn and pick it up
    staged = game.stage_cursor(cur)
    assert staged["mode"] == "target"
    assert staged["from"] == [cur["row"], cur["col"]]
    # Cancel
    back = game.stage_cursor(staged)
    assert back["mode"] == "select"
    assert back["from"] is None


def test_cursor_action_requires_selection(game: Chess):
    cur = game.initial_cursor()
    with pytest.raises(IllegalAction, match="no piece selected"):
        game.cursor_action(cur)


def test_cursor_action_in_target_emits_move(game: Chess):
    cur = game.initial_cursor()
    cur = game.stage_cursor(cur)  # target mode with from=[6,4]
    cur = game.move_cursor(cur, -2, 0)  # target row 4, col 4
    action = game.cursor_action(cur)
    assert action == {"type": "move", "from": [6, 4], "to": [4, 4]}


def test_prepare_action_transitions_to_promote(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[0][4] = "bK"
    b[1][0] = "wP"
    state = _state_with_board(b)
    cur = {
        "mode": "target",
        "row": 0,
        "col": 0,
        "from": [1, 0],
        "promote_idx": 0,
        "pending_to": None,
    }
    new_cur = game.prepare_action(cur, state)
    assert new_cur is not None
    assert new_cur["mode"] == "promote"
    assert new_cur["pending_to"] == [0, 0]


def test_prepare_action_passthrough_on_normal_move(game: Chess, fresh: dict[str, Any]):
    cur = {
        "mode": "target",
        "row": 4,
        "col": 4,
        "from": [6, 4],  # e2 pawn moving to e4 — not a promotion
        "promote_idx": 0,
        "pending_to": None,
    }
    assert game.prepare_action(cur, fresh) is None


def test_promote_cursor_action(game: Chess):
    cur = {
        "mode": "promote",
        "row": 0,
        "col": 0,
        "from": [1, 0],
        "promote_idx": 1,  # R
        "pending_to": [0, 0],
    }
    action = game.cursor_action(cur)
    assert action == {
        "type": "move",
        "from": [1, 0],
        "to": [0, 0],
        "promote": "R",
    }


def test_sync_cursor_resets_after_turn(game: Chess, fresh: dict[str, Any]):
    cur = game.initial_cursor()
    cur = game.stage_cursor(cur)
    assert cur["mode"] == "target"
    synced = game.sync_cursor(cur, fresh)
    assert synced["mode"] == "select"
    assert synced["from"] is None


def test_sync_cursor_preserves_viewer_seat(game: Chess, fresh: dict[str, Any]):
    cur = game.init_cursor_for("bob", fresh)
    cur = game.stage_cursor(cur)
    assert cur["viewer_seat"] == 1
    synced = game.sync_cursor(cur, fresh)
    assert synced["mode"] == "select"
    assert synced["viewer_seat"] == 1


def test_render_smoke(game: Chess, fresh: dict[str, Any]):
    from textual.geometry import Size

    strips = game.render(
        fresh,
        Size(60, 30),
        ui={"cursor": game.initial_cursor(), "player": "alice", "active": True},
    )
    assert len(strips) > SIZE


def test_render_black_flipped(game: Chess, fresh: dict[str, Any]):
    from textual.geometry import Size

    strips = game.render(
        fresh,
        Size(60, 30),
        ui={"cursor": game.initial_cursor(), "player": "bob", "active": True},
    )
    # Just ensure it doesn't raise and produces output
    assert strips


def test_pseudo_moves_pawn_initial(game: Chess, fresh: dict[str, Any]):
    moves = _pseudo_moves(fresh["board"], 6, 4, fresh["castling"], None)
    assert (5, 4) in moves
    assert (4, 4) in moves


def test_in_check_detection(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[0][4] = "bK"
    b[7][0] = "bR"  # attacks white king along 1st rank
    assert _in_check(b, WHITE) is True
    assert _in_check(b, BLACK) is False


def test_init_cursor_for_white_is_seat_0(game: Chess, fresh: dict[str, Any]):
    cur = game.init_cursor_for("alice", fresh)
    assert cur["viewer_seat"] == 0
    assert cur["row"] == 6
    assert cur["col"] == 4
    assert cur["mode"] == "select"


def test_init_cursor_for_black_is_seat_1(game: Chess, fresh: dict[str, Any]):
    cur = game.init_cursor_for("bob", fresh)
    assert cur["viewer_seat"] == 1
    assert cur["row"] == 1
    assert cur["col"] == 4


def test_init_cursor_for_spectator_defaults_to_seat_0(
    game: Chess, fresh: dict[str, Any]
):
    cur = game.init_cursor_for("eve", fresh)
    assert cur["viewer_seat"] == 0
    assert cur["row"] == 6


def test_move_cursor_seat_1_inverts_arrows(game: Chess, fresh: dict[str, Any]):
    cur = game.init_cursor_for("bob", fresh)
    # Start row=1, col=4. "down" arrow (dr=+1) should move toward row 0 for black.
    down = game.move_cursor(cur, 1, 0)
    assert down["row"] == 0
    assert down["col"] == 4
    # "right" arrow (dc=+1) should move toward col 3 (visually right on flipped view).
    right = game.move_cursor(cur, 0, 1)
    assert right["row"] == 1
    assert right["col"] == 3


def test_move_cursor_seat_0_unchanged(game: Chess):
    cur = game.initial_cursor()
    assert cur["viewer_seat"] == 0
    down = game.move_cursor(cur, 1, 0)
    assert down["row"] == 7
    assert down["col"] == 4
    right = game.move_cursor(cur, 0, 1)
    assert right["row"] == 6
    assert right["col"] == 5


def test_stage_cursor_preserves_viewer_seat(game: Chess, fresh: dict[str, Any]):
    cur = game.init_cursor_for("bob", fresh)
    staged = game.stage_cursor(cur)
    assert staged["viewer_seat"] == 1
    assert staged["mode"] == "target"
    assert staged["from"] == [1, 4]


def test_cursor_action_emits_board_coords_regardless_of_seat(game: Chess):
    # Black cursor at board (1, 4) selecting e7, moving to (3, 4) = e5.
    cur = {
        "mode": "target",
        "row": 3,
        "col": 4,
        "from": [1, 4],
        "promote_idx": 0,
        "pending_to": None,
        "viewer_seat": 1,
    }
    action = game.cursor_action(cur)
    assert action == {"type": "move", "from": [1, 4], "to": [3, 4]}


def test_prepare_action_works_with_seat_1_cursor(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[0][4] = "bK"
    b[6][0] = "bP"  # black pawn about to promote at rank 1 = board row 7
    state = _state_with_board(b, turn="bob")
    cur = {
        "mode": "target",
        "row": 7,
        "col": 0,
        "from": [6, 0],
        "promote_idx": 0,
        "pending_to": None,
        "viewer_seat": 1,
    }
    new_cur = game.prepare_action(cur, state)
    assert new_cur is not None
    assert new_cur["mode"] == "promote"
    assert new_cur["pending_to"] == [7, 0]
    assert new_cur["viewer_seat"] == 1


def test_render_seat_1_smoke(game: Chess, fresh: dict[str, Any]):
    from textual.geometry import Size

    cur = game.init_cursor_for("bob", fresh)
    strips = game.render(
        fresh,
        Size(60, 30),
        ui={"cursor": cur, "player": "bob", "active": True},
    )
    assert strips
    assert len(strips) > SIZE


def test_legal_destinations_filters_self_check(game: Chess):
    b = _empty_board()
    b[7][4] = "wK"
    b[6][4] = "wP"
    b[0][4] = "bR"  # pins pawn; pawn is pinned, cannot move off the file
    state_castling = {WHITE: {"K": False, "Q": False}, BLACK: {"K": False, "Q": False}}
    moves = _legal_destinations(b, 6, 4, state_castling, None)
    # pawn can only push along the file (still blocks)
    assert all(c == 4 for _, c in moves)

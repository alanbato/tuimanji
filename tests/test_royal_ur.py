import random

import pytest
from textual.geometry import Size

from tuimanji.engine import IllegalAction
from tuimanji.games.royal_ur import (
    HOME,
    NUM_PIECES,
    POOL,
    P1_TRACK,
    P2_TRACK,
    RoyalUr,
    _cursor_choices,
    _DiceAnimation,
    _MoveAnimation,
    _legal_pieces,
)


@pytest.fixture
def game() -> RoyalUr:
    return RoyalUr()


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch):
    """Make `random.randint` deterministic across the suite by default."""
    monkeypatch.setattr(random, "randint", lambda a, b: 1)


def _force_dice(state: dict, total: int) -> dict:
    """Set the dice array to a sum of `total` (0..4) without rolling."""
    if not (0 <= total <= 4):
        raise ValueError(total)
    dice = [1] * total + [0] * (4 - total)
    return {**state, "dice": list(dice), "phase": "move"}


# ---------- initial state ----------


def test_initial_state(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    assert s["order"] == ["alice", "bob"]
    assert s["turn_player"] == "alice"
    assert s["phase"] == "roll"
    assert s["dice"] is None
    assert s["pieces"]["alice"] == [POOL] * NUM_PIECES
    assert s["pieces"]["bob"] == [POOL] * NUM_PIECES
    assert s["scored"] == {"alice": 0, "bob": 0}
    assert s["winner"] is None


# ---------- roll mechanics ----------


def test_roll_all_ones_yields_sum_4(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"type": "roll"})
    assert s["dice"] == [1, 1, 1, 1]
    assert s["last_roll"] == {"player": "alice", "dice": [1, 1, 1, 1], "sum": 4}
    assert s["phase"] == "move"
    assert s["turn_player"] == "alice"


def test_roll_zero_passes_turn(game: RoyalUr, monkeypatch):
    monkeypatch.setattr(random, "randint", lambda a, b: 0)
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"type": "roll"})
    assert s["dice"] is None
    assert s["phase"] == "roll"
    assert s["turn_player"] == "bob"
    assert s["last_roll"]["sum"] == 0


def test_roll_when_not_your_turn(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="not bob's turn"):
        game.apply_action(s, "bob", {"type": "roll"})


def test_move_before_roll_rejected(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="expected roll"):
        game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})


# ---------- basic movement ----------


def test_enter_piece_from_pool(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s = _force_dice(s, 2)
    s = game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})
    assert s["pieces"]["alice"][0] == 2  # entered at 0+2
    assert s["phase"] == "roll"
    assert s["turn_player"] == "bob"
    assert s["dice"] is None


def test_cannot_move_with_overshoot(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s["pieces"]["alice"][0] = 14  # one short of home
    s = _force_dice(s, 2)
    with pytest.raises(IllegalAction, match="cannot move"):
        game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})


def test_bear_off_requires_exact_roll(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s["pieces"]["alice"][0] = 14
    s = _force_dice(s, 1)
    s = game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})
    assert s["pieces"]["alice"][0] == HOME
    assert s["scored"]["alice"] == 1


def test_cannot_land_on_own_piece(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s["pieces"]["alice"][0] = 5
    s["pieces"]["alice"][1] = 7  # blocks 5+2
    s = _force_dice(s, 2)
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})


# ---------- rosettes ----------


def test_rosette_grants_extra_turn(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s["pieces"]["alice"][0] = 1  # one square from rosette at 4
    s = _force_dice(s, 3)
    s = game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})
    assert s["pieces"]["alice"][0] == 4
    assert s["phase"] == "roll"
    assert s["turn_player"] == "alice"  # extra turn
    assert s["last_move"]["rosette"] is True


def test_central_rosette_blocks_capture(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s["pieces"]["alice"][0] = 7
    s["pieces"]["bob"][0] = 8  # bob is on central rosette
    s = _force_dice(s, 1)  # alice would land on 8
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})


# ---------- captures ----------


def test_capture_sends_opponent_to_pool(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    # Both walk shared lane, same board cell at track 6.
    s["pieces"]["alice"][0] = 5
    s["pieces"]["bob"][3] = 6
    s = _force_dice(s, 1)
    s = game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})
    assert s["pieces"]["alice"][0] == 6
    assert s["pieces"]["bob"][3] == POOL
    assert s["last_move"]["captured_player"] == "bob"
    assert s["last_move"]["captured_idx"] == 3


def test_no_capture_on_own_lane(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s["pieces"]["alice"][0] = 13
    s["pieces"]["bob"][0] = 13  # bob's track 13 is bob's own exit lane
    s = _force_dice(s, 1)
    s = game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})
    # Alice moves to her 14, bob's piece (which lives on bob's 13) is untouched.
    assert s["pieces"]["alice"][0] == 14
    assert s["pieces"]["bob"][0] == 13


# ---------- pass ----------


def test_pass_when_no_legal_moves(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    # All alice pieces at 14; needs exact 1 to bear off. Roll=2 means no moves.
    for i in range(NUM_PIECES):
        s["pieces"]["alice"][i] = 14
    s = _force_dice(s, 2)
    s = game.apply_action(s, "alice", {"type": "pass"})
    assert s["turn_player"] == "bob"
    assert s["phase"] == "roll"


def test_pass_rejected_when_legal_move_exists(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s = _force_dice(s, 2)
    with pytest.raises(IllegalAction, match="cannot pass"):
        game.apply_action(s, "alice", {"type": "pass"})


# ---------- winning ----------


def test_winner_when_all_pieces_home(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    for i in range(NUM_PIECES - 1):
        s["pieces"]["alice"][i] = HOME
    s["scored"]["alice"] = NUM_PIECES - 1
    s["pieces"]["alice"][NUM_PIECES - 1] = 14
    s = _force_dice(s, 1)
    s = game.apply_action(s, "alice", {"type": "move", "piece_idx": NUM_PIECES - 1})
    assert s["winner"] == "alice"
    assert game.is_terminal(s)
    assert game.current_player(s) is None
    # Terminal state stays coherent: phase resets to "roll" and dice are cleared.
    assert s["phase"] == "roll"
    assert s["dice"] is None


# ---------- append-only invariant ----------


def test_apply_roll_does_not_alias_pieces(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s2 = game.apply_action(s, "alice", {"type": "roll"})
    assert s2["pieces"] is not s["pieces"]
    assert s2["pieces"]["alice"] is not s["pieces"]["alice"]
    s2["pieces"]["alice"][0] = 5
    assert s["pieces"]["alice"][0] == POOL  # prev state untouched


def test_apply_pass_does_not_alias_pieces(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    for i in range(NUM_PIECES):
        s["pieces"]["alice"][i] = 14
    s = _force_dice(s, 2)
    s2 = game.apply_action(s, "alice", {"type": "pass"})
    assert s2["pieces"]["alice"] is not s["pieces"]["alice"]


def test_bear_off_clears_dice(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s["pieces"]["alice"][0] = 14
    s = _force_dice(s, 1)
    s = game.apply_action(s, "alice", {"type": "move", "piece_idx": 0})
    assert s["dice"] is None


def test_animation_for_pass_returns_none(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    for i in range(NUM_PIECES):
        s["pieces"]["alice"][i] = 14
    s = _force_dice(s, 2)
    s2 = game.apply_action(s, "alice", {"type": "pass"})
    assert game.animation_for(s, s2) is None


# ---------- _legal_pieces helper ----------


def test_legal_pieces_excludes_blocked(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s["pieces"]["alice"][0] = 5
    s["pieces"]["alice"][1] = 7
    legal = _legal_pieces(s, "alice", 2)
    # Piece 0 would land on 7 (occupied by self) — excluded.
    assert 0 not in legal
    assert 1 in legal  # piece 1 at 7 → 9, fine


# ---------- cursor model ----------


def test_initial_cursor(game: RoyalUr):
    c = game.initial_cursor()
    assert c == {"phase": "roll", "piece_idx": 0, "legal": [], "viewer_seat": 0}


def test_cursor_action_in_roll_phase(game: RoyalUr):
    assert game.cursor_action({"phase": "roll", "piece_idx": 0, "legal": []}) == {
        "type": "roll"
    }


def test_cursor_action_pass_when_no_legal(game: RoyalUr):
    assert game.cursor_action({"phase": "move", "piece_idx": 0, "legal": []}) == {
        "type": "pass"
    }


def test_cursor_action_move(game: RoyalUr):
    assert game.cursor_action(
        {"phase": "move", "piece_idx": 3, "legal": [0, 3, 5]}
    ) == {"type": "move", "piece_idx": 3}


def test_move_cursor_cycles_legal_pieces(game: RoyalUr):
    c = {"phase": "move", "piece_idx": 0, "legal": [0, 2, 5]}
    c = game.move_cursor(c, 0, 1)
    assert c["piece_idx"] == 2
    c = game.move_cursor(c, 0, 1)
    assert c["piece_idx"] == 5
    c = game.move_cursor(c, 0, 1)
    assert c["piece_idx"] == 0
    c = game.move_cursor(c, 0, -1)
    assert c["piece_idx"] == 5


def test_move_cursor_noop_in_roll_phase(game: RoyalUr):
    c = {"phase": "roll", "piece_idx": 0, "legal": []}
    assert game.move_cursor(c, 0, 1) == c


def test_sync_cursor_after_roll(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s = _force_dice(s, 2)
    c = game.sync_cursor({"phase": "roll", "piece_idx": 0, "legal": []}, s)
    assert c["phase"] == "move"
    # Pool pieces collapse to a single cursor choice even though all 7 could
    # technically enter — the player isn't picking an identity, just "enter".
    assert c["legal"] == [0]


def test_cursor_choices_dedupes_pool(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    # 3 in pool, 2 on the board at different positions — expect 3 choices
    # (one pool rep + two board pieces).
    s["pieces"]["alice"] = [POOL, POOL, POOL, 5, 7, HOME, HOME]
    s["scored"]["alice"] = 2
    choices = _cursor_choices(s, "alice", 2)
    # Pool rep is the first pool idx (0); board pieces at 5→7 blocked by self,
    # so only piece 4 (at 7→9) is a legal board choice.
    assert choices == [0, 4]
    # _legal_pieces stays fine-grained for apply_action validation.
    assert _legal_pieces(s, "alice", 2) == [0, 1, 2, 4]


def test_sync_cursor_resets_to_roll_after_terminal(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s["winner"] = "alice"
    c = game.sync_cursor({"phase": "move", "piece_idx": 3, "legal": [3]}, s)
    assert c["phase"] == "roll"
    assert c["legal"] == []


# ---------- animations ----------


def test_dice_animation_for_roll(game: RoyalUr):
    s0 = game.initial_state(["alice", "bob"])
    s1 = game.apply_action(s0, "alice", {"type": "roll"})
    anim = game.animation_for(s0, s1)
    assert isinstance(anim, _DiceAnimation)
    assert anim.final == [1, 1, 1, 1]
    assert anim.frames == len(anim.spins) + 1
    final_frame = anim.overlay(anim.frames - 1)
    assert final_frame["values"] == [1, 1, 1, 1]
    assert final_frame["settled"] is True
    spinning = anim.overlay(0)
    assert spinning["settled"] is False
    assert len(spinning["values"]) == 4


def test_move_animation_walks_intermediate_squares(game: RoyalUr):
    s0 = game.initial_state(["alice", "bob"])
    s0 = _force_dice(s0, 3)
    s1 = game.apply_action(s0, "alice", {"type": "move", "piece_idx": 0})
    anim = game.animation_for(s0, s1)
    assert isinstance(anim, _MoveAnimation)
    # Moving from 0 (pool) → 3 yields 3 frames at positions 1, 2, 3.
    assert len(anim.path_xy) == 3
    assert anim.path_xy[-1] == P1_TRACK[3]
    assert anim.capture_xy is None
    assert anim.frames == 3


def test_move_animation_includes_capture_flash(game: RoyalUr):
    s0 = game.initial_state(["alice", "bob"])
    s0["pieces"]["alice"][0] = 5
    s0["pieces"]["bob"][3] = 6
    s0 = _force_dice(s0, 1)
    s1 = game.apply_action(s0, "alice", {"type": "move", "piece_idx": 0})
    anim = game.animation_for(s0, s1)
    assert isinstance(anim, _MoveAnimation)
    assert anim.capture_xy == P1_TRACK[6]
    assert anim.frames == len(anim.path_xy) + anim.flash_frames


def test_animation_none_when_no_change(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    assert game.animation_for(s, s) is None


# ---------- render ----------


def test_render_returns_strips(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    lines = game.render(
        s,
        Size(80, 24),
        {"player": "alice", "active": True, "cursor": game.initial_cursor()},
    )
    assert all(hasattr(line, "cell_length") for line in lines)


def test_init_cursor_for_sets_viewer_seat(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    assert game.init_cursor_for("alice", s)["viewer_seat"] == 0
    assert game.init_cursor_for("bob", s)["viewer_seat"] == 1


def _render_text(game: RoyalUr, state: dict, viewer_seat: int) -> list[str]:
    cur = {**game.initial_cursor(), "viewer_seat": viewer_seat}
    lines = game.render(
        state, Size(80, 30), {"player": state["order"][viewer_seat], "cursor": cur}
    )
    return ["".join(seg.text for seg in ln._segments) for ln in lines]


def test_render_flips_for_each_viewer(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    # Put a distinctive marker at alice's rosette (track 4 = row 0, col 0) and
    # bob's rosette (track 4 = row 2, col 0). Flipping should swap which row
    # the glyphs appear on.
    s["pieces"]["alice"][0] = 4
    s["pieces"]["bob"][0] = 4

    def _first_player_line(view: list[str]) -> str:
        return next(ln for ln in view if "home" in ln)

    def _last_player_line(view: list[str]) -> str:
        return next(ln for ln in reversed(view) if "home" in ln)

    alice_view = _render_text(game, s, viewer_seat=0)
    bob_view = _render_text(game, s, viewer_seat=1)

    # Own lane renders at the bottom (nearest the viewer), opponent on top.
    assert "bob" in _first_player_line(alice_view)
    assert "alice" in _last_player_line(alice_view)
    assert "alice" in _first_player_line(bob_view)
    assert "bob" in _last_player_line(bob_view)


def test_render_handles_dice_overlay(game: RoyalUr):
    s = game.initial_state(["alice", "bob"])
    s = _force_dice(s, 3)
    lines = game.render(
        s,
        Size(80, 24),
        {
            "player": "alice",
            "active": True,
            "cursor": {"phase": "move", "piece_idx": 0, "legal": [0]},
            "animation": {
                "kind": "dice",
                "values": [1, 0, 1, 1],
                "sum": 3,
                "settled": True,
            },
        },
    )
    assert all(hasattr(line, "cell_length") for line in lines)


def test_track_constants_consistent():
    """Both tracks share the middle lane (squares 5..12)."""
    for pos in range(5, 13):
        assert P1_TRACK[pos] == P2_TRACK[pos]
    # Entry/exit lanes are disjoint between players (different rows).
    for pos in (1, 2, 3, 4, 13, 14):
        assert P1_TRACK[pos] != P2_TRACK[pos]

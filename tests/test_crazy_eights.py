import random

import pytest

from tuimanji.engine import IllegalAction
from tuimanji.games.crazy_eights import (
    CrazyEights,
    _can_play,
    _is_eight,
    _suit,
)


@pytest.fixture
def game() -> CrazyEights:
    return CrazyEights()


def _make_state(**overrides):
    base = {
        "deck": ["AS", "2H", "3D", "4C", "5S"],
        "discard": ["7H"],
        "hands": {
            "alice": ["AH", "KS", "8D", "3C", "JS"],
            "bob": ["2S", "QH", "9D", "6C", "TC"],
        },
        "order": ["alice", "bob"],
        "turn_player": "alice",
        "current_suit": "H",
        "winner": None,
        "card_counts": {"alice": 5, "bob": 5},
    }
    base.update(overrides)
    return base


# --- initial_state ---


def test_initial_state_two_players(game: CrazyEights):
    random.seed(42)
    s = game.initial_state(["alice", "bob"])
    assert len(s["hands"]["alice"]) == 5
    assert len(s["hands"]["bob"]) == 5
    assert len(s["discard"]) == 1
    assert len(s["deck"]) == 52 - 10 - 1
    assert s["current_suit"] == _suit(s["discard"][0])
    assert s["turn_player"] == "alice"
    assert s["winner"] is None


def test_initial_state_four_players(game: CrazyEights):
    random.seed(99)
    s = game.initial_state(["a", "b", "c", "d"])
    for p in ["a", "b", "c", "d"]:
        assert len(s["hands"][p]) == 5
    assert len(s["deck"]) == 52 - 20 - 1


def test_initial_starter_not_eight(game: CrazyEights):
    for seed in range(200):
        random.seed(seed)
        s = game.initial_state(["alice", "bob"])
        assert not _is_eight(s["discard"][0])


# --- apply_action: play card ---


def test_play_matching_suit(game: CrazyEights):
    s = _make_state()
    s2 = game.apply_action(s, "alice", {"type": "play", "index": 0})
    assert "AH" not in s2["hands"]["alice"]
    assert s2["discard"][-1] == "AH"
    assert s2["turn_player"] == "bob"
    assert s2["current_suit"] == "H"


def test_play_matching_rank(game: CrazyEights):
    s = _make_state(current_suit="S")
    s["discard"] = ["3S"]
    s2 = game.apply_action(s, "alice", {"type": "play", "index": 3})
    assert s2["discard"][-1] == "3C"
    assert s2["current_suit"] == "C"
    assert s2["turn_player"] == "bob"


def test_play_invalid_card(game: CrazyEights):
    s = _make_state()
    with pytest.raises(IllegalAction, match="doesn't match"):
        game.apply_action(s, "alice", {"type": "play", "index": 1})


def test_index_wraps_to_draw(game: CrazyEights):
    s = _make_state(hands={"alice": ["AH"], "bob": ["2S"]})
    s["card_counts"] = {"alice": 1, "bob": 1}
    s2 = game.apply_action(s, "alice", {"type": "play", "index": 5})
    assert len(s2["hands"]["alice"]) == 2
    assert s2["turn_player"] == "bob"


def test_play_wrong_turn(game: CrazyEights):
    s = _make_state()
    with pytest.raises(IllegalAction, match="not your turn"):
        game.apply_action(s, "bob", {"type": "play", "index": 0})


def test_play_game_over(game: CrazyEights):
    s = _make_state(winner="alice")
    with pytest.raises(IllegalAction, match="game is over"):
        game.apply_action(s, "alice", {"type": "play", "index": 0})


# --- apply_action: play 8 ---


def test_play_eight_with_suit(game: CrazyEights):
    s = _make_state()
    s2 = game.apply_action(s, "alice", {"type": "play", "index": 2, "chosen_suit": "S"})
    assert s2["discard"][-1] == "8D"
    assert s2["current_suit"] == "S"
    assert "8D" not in s2["hands"]["alice"]


def test_play_eight_without_suit(game: CrazyEights):
    s = _make_state()
    with pytest.raises(IllegalAction, match="must choose a suit"):
        game.apply_action(s, "alice", {"type": "play", "index": 2})


def test_play_eight_invalid_suit(game: CrazyEights):
    s = _make_state()
    with pytest.raises(IllegalAction, match="must choose a suit"):
        game.apply_action(s, "alice", {"type": "play", "index": 2, "chosen_suit": "X"})


# --- apply_action: draw ---


def test_draw_adds_card(game: CrazyEights):
    s = _make_state()
    s2 = game.apply_action(s, "alice", {"type": "play", "index": 5})
    assert len(s2["hands"]["alice"]) == 6
    assert len(s2["deck"]) == len(s["deck"]) - 1
    assert s2["turn_player"] == "bob"


def test_draw_reshuffles_empty_deck(game: CrazyEights):
    s = _make_state(
        deck=[],
        discard=["3S", "KH", "7H"],
    )
    random.seed(0)
    s2 = game.apply_action(s, "alice", {"type": "play", "index": 5})
    assert len(s2["hands"]["alice"]) == 6
    assert len(s2["deck"]) + len(s2["discard"]) == 2
    assert s2["discard"][-1] == "7H"


def test_draw_completely_exhausted(game: CrazyEights):
    s = _make_state(deck=[], discard=["7H"])
    with pytest.raises(IllegalAction, match="no cards left"):
        game.apply_action(s, "alice", {"type": "play", "index": 5})


# --- win / draw conditions ---


def test_win_on_last_card(game: CrazyEights):
    s = _make_state(
        hands={"alice": ["AH"], "bob": ["2S"]},
        card_counts={"alice": 1, "bob": 1},
    )
    s2 = game.apply_action(s, "alice", {"type": "play", "index": 0})
    assert s2["winner"] == "alice"
    assert game.is_terminal(s2)
    assert game.winner(s2) == "alice"
    assert game.current_player(s2) is None


def test_win_on_last_card_eight(game: CrazyEights):
    s = _make_state(
        hands={"alice": ["8H"], "bob": ["2S"]},
        card_counts={"alice": 1, "bob": 1},
    )
    s2 = game.apply_action(s, "alice", {"type": "play", "index": 0, "chosen_suit": "C"})
    assert s2["winner"] == "alice"


def test_draw_game(game: CrazyEights):
    s2 = _make_state(
        deck=[],
        discard=["2D", "7H"],
        hands={"alice": ["KS"], "bob": ["QC"]},
        card_counts={"alice": 1, "bob": 1},
        current_suit="H",
    )
    # alice draws from reshuffled discard (2D)
    random.seed(0)
    s3 = game.apply_action(s2, "alice", {"type": "play", "index": 1})
    # After alice draws, deck is empty again and no one can play
    # Current suit H, top discard 7H, alice has KS + 2D, bob has QC
    # KS: suit S≠H, rank K≠7 → can't play
    # 2D: suit D≠H, rank 2≠7 → can't play
    # QC: suit C≠H, rank Q≠7 → can't play
    # But discard pile still has [7H] and deck is [], reshuffleable = 0
    assert s3["winner"] == "draw"
    assert game.is_terminal(s3)
    assert game.winner(s3) is None


# --- turn cycling ---


def test_turn_cycles_three_players(game: CrazyEights):
    s = _make_state(
        order=["alice", "bob", "charlie"],
        hands={
            "alice": ["AH", "KH"],
            "bob": ["2H", "QH"],
            "charlie": ["3H", "JH"],
        },
        card_counts={"alice": 2, "bob": 2, "charlie": 2},
    )
    s2 = game.apply_action(s, "alice", {"type": "play", "index": 0})
    assert s2["turn_player"] == "bob"
    s3 = game.apply_action(s2, "bob", {"type": "play", "index": 0})
    assert s3["turn_player"] == "charlie"
    s4 = game.apply_action(s3, "charlie", {"type": "play", "index": 0})
    assert s4["turn_player"] == "alice"


# --- protocol queries ---


def test_current_player_during_game(game: CrazyEights):
    s = _make_state()
    assert game.current_player(s) == "alice"


def test_current_player_when_terminal(game: CrazyEights):
    s = _make_state(winner="alice")
    assert game.current_player(s) is None


def test_winner_returns_none_on_draw(game: CrazyEights):
    s = _make_state(winner="draw")
    assert game.winner(s) is None
    assert game.is_terminal(s)


# --- cursor model ---


def test_initial_cursor(game: CrazyEights):
    c = game.initial_cursor()
    assert c["phase"] == "hand"
    assert c["index"] == 0
    assert c["suit_index"] == 0


def test_move_cursor_hand_phase(game: CrazyEights):
    c = game.initial_cursor()
    c2 = game.move_cursor(c, 0, 1)
    assert c2["index"] == 1
    c3 = game.move_cursor(c, 0, -1)
    assert c3["index"] == -1


def test_move_cursor_suit_phase(game: CrazyEights):
    c = {"index": 2, "phase": "suit", "suit_index": 0}
    c2 = game.move_cursor(c, 0, 1)
    assert c2["suit_index"] == 1
    c3 = game.move_cursor(c, 0, -1)
    assert c3["suit_index"] == 3


def test_cursor_action_play(game: CrazyEights):
    c = {"index": 2, "phase": "hand", "suit_index": 0}
    a = game.cursor_action(c)
    assert a == {"type": "play", "index": 2}


def test_cursor_action_suit(game: CrazyEights):
    c = {"index": 2, "phase": "suit", "suit_index": 1}
    a = game.cursor_action(c)
    assert a == {"type": "play", "index": 2, "chosen_suit": "H"}


# --- prepare_action ---


def test_prepare_action_eight_enters_suit_phase(game: CrazyEights):
    s = _make_state()
    c = {"index": 2, "phase": "hand", "suit_index": 0}
    result = game.prepare_action(c, s)
    assert result is not None
    assert result["phase"] == "suit"
    assert result["index"] == 2


def test_prepare_action_non_eight_proceeds(game: CrazyEights):
    s = _make_state()
    c = {"index": 0, "phase": "hand", "suit_index": 0}
    assert game.prepare_action(c, s) is None


def test_prepare_action_draw_proceeds(game: CrazyEights):
    s = _make_state()
    c = {"index": 5, "phase": "hand", "suit_index": 0}
    assert game.prepare_action(c, s) is None


def test_prepare_action_suit_phase_proceeds(game: CrazyEights):
    s = _make_state()
    c = {"index": 2, "phase": "suit", "suit_index": 1}
    assert game.prepare_action(c, s) is None


# --- sync_cursor ---


def test_sync_cursor_resets_phase(game: CrazyEights):
    s = _make_state()
    c = {"index": 2, "phase": "suit", "suit_index": 3}
    result = game.sync_cursor(c, s)
    assert result["phase"] == "hand"
    assert result["suit_index"] == 0
    assert result["index"] == 2


# --- render ---


def test_render_returns_strips(game: CrazyEights):
    s = _make_state()
    from textual.geometry import Size

    strips = game.render(s, Size(80, 24), {"player": "alice"})
    assert len(strips) > 0
    assert all(hasattr(strip, "cell_length") for strip in strips)


def test_render_hides_opponent_hand(game: CrazyEights):
    s = _make_state()
    from textual.geometry import Size

    strips = game.render(s, Size(80, 24), {"player": "alice"})
    text = ""
    for strip in strips:
        for seg in strip._segments:
            text += seg.text

    for card in s["hands"]["bob"]:
        from tuimanji.games.crazy_eights import _card_glyph

        assert _card_glyph(card) not in text


def test_render_shows_suit_picker(game: CrazyEights):
    s = _make_state()
    from textual.geometry import Size

    cursor = {"index": 2, "phase": "suit", "suit_index": 0}
    strips = game.render(s, Size(80, 24), {"player": "alice", "cursor": cursor})
    text = ""
    for strip in strips:
        for seg in strip._segments:
            text += seg.text
    assert "Choose suit" in text


# --- helpers ---


def test_can_play_matching_suit():
    assert _can_play("AH", "H", "3")


def test_can_play_matching_rank():
    assert _can_play("3S", "H", "3")


def test_can_play_eight_always():
    assert _can_play("8D", "S", "K")


def test_cannot_play_mismatch():
    assert not _can_play("KS", "H", "3")

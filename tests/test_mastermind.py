from typing import Any

import pytest
from textual.geometry import Size

from tuimanji.engine import IllegalAction
from tuimanji.games.mastermind import (
    CODE_LEN,
    MAX_GUESSES,
    MAX_ROUNDS,
    Mastermind,
    _score_guess,
)


@pytest.fixture
def game() -> Mastermind:
    return Mastermind()


# ---------- pure scoring ----------


def test_score_all_correct():
    assert _score_guess([1, 2, 3, 4], [1, 2, 3, 4]) == (4, 0)


def test_score_all_wrong():
    assert _score_guess([1, 2, 3, 4], [5, 5, 5, 5]) == (0, 0)


def test_score_partial_position_only():
    # First slot is exact; nothing else overlaps.
    assert _score_guess([1, 2, 3, 4], [1, 5, 5, 5]) == (1, 0)


def test_score_partial_color_only():
    # No exact matches, but colors 1 and 4 swap → all white pegs.
    assert _score_guess([1, 2, 3, 4], [4, 3, 2, 1]) == (0, 4)


def test_score_handles_duplicates_in_guess():
    # Code has one 1; guess has two 1s — only one peg should count.
    assert _score_guess([1, 2, 3, 4], [1, 1, 5, 5]) == (1, 0)


def test_score_handles_duplicates_in_code():
    # Code has two 1s; guess has one 1 in wrong position → one white.
    assert _score_guess([1, 1, 2, 2], [3, 3, 1, 4]) == (0, 1)


def test_score_mixed_black_and_white():
    assert _score_guess([1, 2, 3, 4], [1, 3, 2, 5]) == (1, 2)


# ---------- lifecycle ----------


def test_initial_state(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    assert s["phase"] == "set"
    assert s["round"] == 0
    assert s["round_wins"] == {"alice": 0, "bob": 0}
    assert s["round_history"] == []
    assert s["current"]["maker"] == "alice"
    assert s["current"]["breaker"] == "bob"
    assert s["current"]["code"] is None
    assert s["current"]["guesses"] == []
    assert s["turn_player"] == "alice"
    assert s["winner"] is None


def test_initial_state_rejects_wrong_player_count(game: Mastermind):
    with pytest.raises(ValueError):
        game.initial_state(["solo"])
    with pytest.raises(ValueError):
        game.initial_state(["a", "b", "c"])


# ---------- set phase ----------


def test_set_advances_to_guess_phase(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"code": [1, 2, 3, 4]})
    assert s["phase"] == "guess"
    assert s["current"]["code"] == [1, 2, 3, 4]
    assert s["turn_player"] == "bob"


def test_set_rejects_wrong_player(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="turn"):
        game.apply_action(s, "bob", {"code": [1, 2, 3, 4]})


def test_set_rejects_wrong_length(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match=f"{CODE_LEN}"):
        game.apply_action(s, "alice", {"code": [1, 2, 3]})


def test_set_rejects_color_out_of_range(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction, match="range"):
        game.apply_action(s, "alice", {"code": [1, 2, 3, 7]})
    with pytest.raises(IllegalAction, match="range"):
        game.apply_action(s, "alice", {"code": [0, 2, 3, 4]})


def test_set_allows_duplicates(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"code": [1, 1, 1, 1]})
    assert s["current"]["code"] == [1, 1, 1, 1]


# ---------- guess phase ----------


def _set_then_guess(game: Mastermind, code: list[int]) -> dict[str, Any]:
    s = game.initial_state(["alice", "bob"])
    return game.apply_action(s, "alice", {"code": code})


def test_guess_records_feedback(game: Mastermind):
    s = _set_then_guess(game, [1, 2, 3, 4])
    s = game.apply_action(s, "bob", {"code": [1, 3, 2, 5]})
    g = s["current"]["guesses"][0]
    assert g["guess"] == [1, 3, 2, 5]
    assert g["black"] == 1
    assert g["white"] == 2
    assert s["phase"] == "guess"
    assert s["turn_player"] == "bob"


def test_guess_rejects_wrong_player(game: Mastermind):
    s = _set_then_guess(game, [1, 2, 3, 4])
    with pytest.raises(IllegalAction, match="turn"):
        game.apply_action(s, "alice", {"code": [1, 2, 3, 4]})


def test_guess_rejects_invalid_code(game: Mastermind):
    s = _set_then_guess(game, [1, 2, 3, 4])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "bob", {"code": [1, 2, 3]})
    with pytest.raises(IllegalAction, match="range"):
        game.apply_action(s, "bob", {"code": [1, 2, 3, 99]})


def test_cracking_code_ends_round_breaker_wins(game: Mastermind):
    s = _set_then_guess(game, [1, 2, 3, 4])
    s = game.apply_action(s, "bob", {"code": [1, 2, 3, 4]})
    # Round 0 ends; bob (breaker) wins it.
    assert s["round_history"][0]["winner"] == "bob"
    assert s["round_history"][0]["cracked"] is True
    assert s["round_wins"]["bob"] == 1
    # Roles swap for round 1.
    assert s["round"] == 1
    assert s["phase"] == "set"
    assert s["current"]["maker"] == "bob"
    assert s["current"]["breaker"] == "alice"
    assert s["turn_player"] == "bob"


def test_exhausting_guesses_ends_round_maker_wins(game: Mastermind):
    s = _set_then_guess(game, [1, 1, 1, 1])
    # Guess wrong MAX_GUESSES times in a row.
    for i in range(MAX_GUESSES):
        s = game.apply_action(s, "bob", {"code": [2, 2, 2, 2]})
        if s["phase"] != "guess":
            break
    last = s["round_history"][0]
    assert last["winner"] == "alice"
    assert last["cracked"] is False
    assert len(last["guesses"]) == MAX_GUESSES
    assert s["round_wins"]["alice"] == 1


# ---------- best-of-3 progression ----------


def _play_round(
    game: Mastermind,
    s: dict[str, Any],
    code: list[int],
    breaker_wins: bool,
) -> dict[str, Any]:
    """Play out one round: maker sets ``code``, breaker either cracks it or
    burns through MAX_GUESSES of misses."""
    maker = s["current"]["maker"]
    breaker = s["current"]["breaker"]
    s = game.apply_action(s, maker, {"code": code})
    if breaker_wins:
        s = game.apply_action(s, breaker, {"code": code})
        return s
    # Pick a guess that scores nothing — flip every color to (color%6)+1.
    bad = [((c % 6) + 1) for c in code]
    # Ensure bad really is wrong (possible only if all colors differ; with 6
    # colors and a length-4 code at most 4 of 6 colors appear, so bad shares
    # no positional matches; intentional miss).
    for _ in range(MAX_GUESSES):
        s = game.apply_action(s, breaker, {"code": bad})
        if s["phase"] != "guess":
            break
    return s


def test_match_ends_when_player_reaches_two_wins(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    # Round 0: alice maker, bob breaker — bob cracks → bob 1-0.
    s = _play_round(game, s, [1, 2, 3, 4], breaker_wins=True)
    assert s["round_wins"] == {"alice": 0, "bob": 1}
    assert s["phase"] == "set"
    # Round 1: bob maker, alice breaker — alice fails → bob 2-0.
    s = _play_round(game, s, [1, 1, 1, 1], breaker_wins=False)
    assert s["round_wins"] == {"alice": 0, "bob": 2}
    assert s["phase"] == "finished"
    assert s["winner"] == "bob"
    assert game.is_terminal(s) is True
    assert game.current_player(s) is None


def test_match_goes_to_third_round_on_split(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    # Round 0: bob cracks → 0-1
    s = _play_round(game, s, [1, 2, 3, 4], breaker_wins=True)
    # Round 1: alice (now breaker) cracks → 1-1
    s = _play_round(game, s, [4, 3, 2, 1], breaker_wins=True)
    assert s["round_wins"] == {"alice": 1, "bob": 1}
    assert s["round"] == 2
    assert s["phase"] == "set"
    # Round 2 (tiebreaker): alice maker again, bob breaker
    assert s["current"]["maker"] == "alice"
    assert s["current"]["breaker"] == "bob"
    s = _play_round(game, s, [5, 5, 5, 5], breaker_wins=False)
    assert s["phase"] == "finished"
    assert s["winner"] == "alice"
    assert s["round_wins"]["alice"] == 2
    assert len(s["round_history"]) == MAX_ROUNDS


def test_post_finish_actions_rejected(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    # Round 0: bob cracks → 0-1
    s = _play_round(game, s, [1, 2, 3, 4], breaker_wins=True)
    # Round 1: alice (now breaker) cracks → 1-1
    s = _play_round(game, s, [4, 3, 2, 1], breaker_wins=True)
    # Round 2 tiebreaker: alice is maker again, bob is breaker; bob fails → 2-1
    s = _play_round(game, s, [6, 6, 6, 6], breaker_wins=False)
    assert s["phase"] == "finished"
    with pytest.raises(IllegalAction, match="game is over"):
        game.apply_action(s, s["order"][0], {"code": [1, 2, 3, 4]})


# ---------- cursor model ----------


def test_initial_cursor(game: Mastermind):
    cur = game.initial_cursor()
    assert cur["pos"] == 0
    assert cur["code"] == [1, 1, 1, 1]
    assert cur["phase"] == "set"


def test_cursor_horizontal_wrap(game: Mastermind):
    cur = game.initial_cursor()
    cur = game.move_cursor(cur, 0, -1)
    assert cur["pos"] == CODE_LEN - 1
    cur = game.move_cursor(cur, 0, 1)
    assert cur["pos"] == 0


def test_cursor_vertical_changes_color(game: Mastermind):
    cur = game.initial_cursor()
    # Up arrow (dr=-1) cycles forward.
    cur = game.move_cursor(cur, -1, 0)
    assert cur["code"][0] == 2
    cur = game.move_cursor(cur, -1, 0)
    assert cur["code"][0] == 3
    # Down wraps backward from 1 → 6.
    cur = game.initial_cursor()
    cur = game.move_cursor(cur, 1, 0)
    assert cur["code"][0] == 6


def test_cursor_action_returns_code(game: Mastermind):
    cur = game.initial_cursor()
    cur = game.move_cursor(cur, 0, 1)
    cur = game.move_cursor(cur, -1, 0)
    assert game.cursor_action(cur) == {"code": cur["code"]}


def test_sync_cursor_resets_on_phase_change(game: Mastermind):
    cur = game.initial_cursor()
    cur = game.move_cursor(cur, -1, 0)
    cur = game.move_cursor(cur, 0, 1)
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"code": [1, 2, 3, 4]})
    new_cur = game.sync_cursor(cur, s)
    assert new_cur != cur
    assert new_cur["phase"] == "guess"
    assert new_cur["pos"] == 0
    assert new_cur["code"] == [1, 1, 1, 1]


def test_sync_cursor_noop_when_phase_matches(game: Mastermind):
    cur = game.initial_cursor()
    cur = game.move_cursor(cur, -1, 0)
    s = game.initial_state(["alice", "bob"])
    new_cur = game.sync_cursor(cur, s)
    assert new_cur is cur


# ---------- protocol queries ----------


def test_current_player_during_play(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    assert game.current_player(s) == "alice"
    s = game.apply_action(s, "alice", {"code": [1, 2, 3, 4]})
    assert game.current_player(s) == "bob"


def test_winner_none_in_progress(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    assert game.winner(s) is None


def test_animation_for_returns_none(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    s2 = game.apply_action(s, "alice", {"code": [1, 2, 3, 4]})
    assert game.animation_for(s, s2) is None


# ---------- render ----------


def test_render_does_not_leak_secret_to_breaker(game: Mastermind):
    s = _set_then_guess(game, [1, 2, 3, 4])
    lines = game.render(
        s, Size(80, 40), {"player": "bob", "cursor": game.initial_cursor()}
    )
    text = "\n".join("".join(seg.text for seg in strip._segments) for strip in lines)
    # Color labels for 1,2,3,4 are R O M G; none should appear in the secret row.
    secret_row = [line for line in text.split("\n") if "secret:" in line][0]
    for label in ("R", "O", "M", "G"):
        assert f" {label} " not in secret_row, (
            f"breaker should not see {label} in secret row: {secret_row!r}"
        )


def test_render_reveals_secret_to_maker(game: Mastermind):
    s = _set_then_guess(game, [1, 2, 3, 4])
    lines = game.render(
        s, Size(80, 40), {"player": "alice", "cursor": game.initial_cursor()}
    )
    text = "\n".join("".join(seg.text for seg in strip._segments) for strip in lines)
    secret_row = [line for line in text.split("\n") if "secret:" in line][0]
    # All four labels should appear in order.
    labels_seen = "".join(ch for ch in secret_row if ch in "ROMGBW")
    assert labels_seen.startswith("ROMG")


def test_render_finished_reveals_secret_to_anyone(game: Mastermind):
    s = game.initial_state(["alice", "bob"])
    # Two consecutive breaker wins (with role swap → different breakers) leave
    # the score 1-1, then the tiebreaker third round ends the match.
    s = _play_round(game, s, [1, 2, 3, 4], breaker_wins=True)
    s = _play_round(game, s, [4, 3, 2, 1], breaker_wins=True)
    s = _play_round(game, s, [6, 6, 6, 6], breaker_wins=False)
    assert s["phase"] == "finished"
    lines = game.render(s, Size(80, 40), {"player": "bob"})
    text = "\n".join("".join(seg.text for seg in strip._segments) for strip in lines)
    assert "match winner" in text

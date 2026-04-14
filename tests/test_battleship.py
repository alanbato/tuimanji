from typing import Any

import pytest

from tuimanji.engine import IllegalAction
from tuimanji.games.battleship import FLEET, SIZE, Battleship, ExplodeAnimation


@pytest.fixture
def game() -> Battleship:
    return Battleship()


def _valid_fleet() -> list[dict[str, Any]]:
    """Place each ship on its own row, horizontally starting at col 0."""
    return [
        {"name": name, "row": idx, "col": 0, "dir": "h"}
        for idx, (name, _length, _mark) in enumerate(FLEET)
    ]


def _placed_state(game: Battleship) -> dict[str, Any]:
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"type": "place_fleet", "ships": _valid_fleet()})
    s = game.apply_action(s, "bob", {"type": "place_fleet", "ships": _valid_fleet()})
    return s


def test_initial_state(game: Battleship):
    s = game.initial_state(["alice", "bob"])
    assert s["phase"] == "placement"
    assert s["turn_player"] == "alice"
    assert s["winner"] is None
    assert s["placed"] == {"alice": False, "bob": False}
    assert all(c == "." for row in s["boards"]["alice"] for c in row)
    assert all(c == "." for row in s["shots"]["alice"] for c in row)


def test_place_fleet_advances_turn(game: Battleship):
    s = game.initial_state(["alice", "bob"])
    s = game.apply_action(s, "alice", {"type": "place_fleet", "ships": _valid_fleet()})
    assert s["placed"]["alice"] is True
    assert s["placed"]["bob"] is False
    assert s["phase"] == "placement"
    assert s["turn_player"] == "bob"


def test_both_placed_starts_battle(game: Battleship):
    s = _placed_state(game)
    assert s["phase"] == "battle"
    assert s["turn_player"] == "alice"


def test_place_fleet_rejects_missing_ships(game: Battleship):
    s = game.initial_state(["alice", "bob"])
    short = _valid_fleet()[:-1]
    with pytest.raises(IllegalAction, match="exactly"):
        game.apply_action(s, "alice", {"type": "place_fleet", "ships": short})


def test_place_fleet_rejects_out_of_bounds(game: Battleship):
    s = game.initial_state(["alice", "bob"])
    bad = _valid_fleet()
    bad[0]["col"] = SIZE - 1  # carrier length 5 → off the board
    with pytest.raises(IllegalAction, match="bounds"):
        game.apply_action(s, "alice", {"type": "place_fleet", "ships": bad})


def test_place_fleet_rejects_overlap(game: Battleship):
    s = game.initial_state(["alice", "bob"])
    bad = _valid_fleet()
    bad[1] = {"name": "Battleship", "row": 0, "col": 0, "dir": "h"}  # overlaps Carrier
    with pytest.raises(IllegalAction, match="overlap"):
        game.apply_action(s, "alice", {"type": "place_fleet", "ships": bad})


def test_fire_during_placement_rejected(game: Battleship):
    s = game.initial_state(["alice", "bob"])
    with pytest.raises(IllegalAction):
        game.apply_action(s, "alice", {"type": "fire", "row": 0, "col": 0})


def test_fire_miss(game: Battleship):
    s = _placed_state(game)
    # Bob's fleet sits in rows 0..4. Row 9 is open water.
    s = game.apply_action(s, "alice", {"type": "fire", "row": 9, "col": 9})
    assert s["shots"]["bob"][9][9] == "M"
    assert s["last_shot"]["hit"] is False
    assert s["turn_player"] == "bob"


def test_fire_hit(game: Battleship):
    s = _placed_state(game)
    s = game.apply_action(s, "alice", {"type": "fire", "row": 0, "col": 0})
    assert s["shots"]["bob"][0][0] == "H"
    assert s["last_shot"]["hit"] is True


def test_fire_already_shot_rejected(game: Battleship):
    s = _placed_state(game)
    s = game.apply_action(s, "alice", {"type": "fire", "row": 9, "col": 9})
    s = game.apply_action(s, "bob", {"type": "fire", "row": 9, "col": 9})
    with pytest.raises(IllegalAction, match="already"):
        game.apply_action(s, "alice", {"type": "fire", "row": 9, "col": 9})


def test_sink_ship(game: Battleship):
    s = _placed_state(game)
    # Destroyer is row 4, len 2, cols 0..1. Two hits sink it.
    s = game.apply_action(s, "alice", {"type": "fire", "row": 4, "col": 0})
    s = game.apply_action(s, "bob", {"type": "fire", "row": 9, "col": 0})
    s = game.apply_action(s, "alice", {"type": "fire", "row": 4, "col": 1})
    destroyer = next(sh for sh in s["fleets"]["bob"] if sh["name"] == "Destroyer")
    assert destroyer["sunk"] is True
    assert s["last_shot"]["sunk"] == "Destroyer"


def test_winner_when_all_sunk(game: Battleship):
    s = _placed_state(game)
    # Alice sinks every bob ship by walking each one's cells. Bob fires harmless misses.
    bob_fleet = list(s["fleets"]["bob"])
    miss_targets = [(8 + (i // SIZE), i % SIZE) for i in range(2 * SIZE)]
    miss_iter = iter(miss_targets)
    for ship in bob_fleet:
        for cell in ship["cells"]:
            r, c = cell
            s = game.apply_action(s, "alice", {"type": "fire", "row": r, "col": c})
            if s["winner"] is not None:
                break
            mr, mc = next(miss_iter)
            s = game.apply_action(s, "bob", {"type": "fire", "row": mr, "col": mc})
        if s["winner"] is not None:
            break
    assert s["winner"] == "alice"
    assert s["phase"] == "finished"
    assert game.is_terminal(s)
    assert game.current_player(s) is None


def test_animation_for_hit_and_miss(game: Battleship):
    s0 = _placed_state(game)
    s_hit = game.apply_action(s0, "alice", {"type": "fire", "row": 0, "col": 0})
    anim = game.animation_for(s0, s_hit)
    assert isinstance(anim, ExplodeAnimation)
    assert anim.row == 0 and anim.col == 0
    assert anim.frames == 4
    assert anim.overlay(0)["glyph"] == "O"
    assert anim.overlay(3)["glyph"] == "X"

    s_miss = game.apply_action(s_hit, "bob", {"type": "fire", "row": 9, "col": 9})
    assert game.animation_for(s_hit, s_miss) is None


def test_cursor_wraps(game: Battleship):
    cur = game.initial_cursor()
    cur = game.move_cursor(cur, -1, -1)
    assert cur["row"] == SIZE - 1
    assert cur["col"] == SIZE - 1
    cur = game.move_cursor(cur, 1, 1)
    assert cur["row"] == 0 and cur["col"] == 0


def test_rotate_cursor(game: Battleship):
    cur = game.initial_cursor()
    assert cur["dir"] == "h"
    cur = game.rotate_cursor(cur)
    assert cur["dir"] == "v"
    cur = game.rotate_cursor(cur)
    assert cur["dir"] == "h"


def test_stage_cursor_advances_and_rejects_overlap(game: Battleship):
    cur = game.initial_cursor()
    cur = game.stage_cursor(cur)  # stage Carrier at (0,0) horizontal
    assert cur["ship_idx"] == 1
    assert len(cur["placed"]) == 1
    # Try to stage Battleship overlapping the Carrier
    with pytest.raises(IllegalAction, match="overlap"):
        game.stage_cursor(cur)


def test_cursor_action_requires_full_fleet(game: Battleship):
    cur = game.initial_cursor()
    with pytest.raises(IllegalAction, match="place all ships"):
        game.cursor_action(cur)


def test_place_fleet_rejects_unknown_ship(game: Battleship):
    s = game.initial_state(["alice", "bob"])
    bad = _valid_fleet()
    bad[0]["name"] = "Dreadnought"
    with pytest.raises(IllegalAction, match="unknown ship"):
        game.apply_action(s, "alice", {"type": "place_fleet", "ships": bad})


def test_place_fleet_rejects_duplicate(game: Battleship):
    s = game.initial_state(["alice", "bob"])
    bad = _valid_fleet()
    bad[1]["name"] = bad[0]["name"]
    with pytest.raises(IllegalAction, match="duplicate|missing"):
        game.apply_action(s, "alice", {"type": "place_fleet", "ships": bad})


def test_place_fleet_vertical_direction(game: Battleship):
    s = game.initial_state(["alice", "bob"])
    vertical = [
        {"name": name, "row": 0, "col": idx, "dir": "v"}
        for idx, (name, _length, _mark) in enumerate(FLEET)
    ]
    s = game.apply_action(s, "alice", {"type": "place_fleet", "ships": vertical})
    assert s["placed"]["alice"] is True


def test_fire_out_of_turn_rejected(game: Battleship):
    s = _placed_state(game)
    with pytest.raises(IllegalAction, match="turn"):
        game.apply_action(s, "bob", {"type": "fire", "row": 0, "col": 0})


def test_turn_switches_after_hit(game: Battleship):
    s = _placed_state(game)
    s = game.apply_action(s, "alice", {"type": "fire", "row": 0, "col": 0})
    assert s["last_shot"]["hit"] is True
    assert s["turn_player"] == "bob"


def test_sync_cursor_switches_to_battle(game: Battleship):
    s = _placed_state(game)
    cur = game.initial_cursor()
    new_cur = game.sync_cursor(cur, s)
    assert new_cur["mode"] == "battle"
    assert new_cur["row"] == 0 and new_cur["col"] == 0

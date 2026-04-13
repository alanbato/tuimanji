import pytest

from tuimanji import store
from tuimanji.db import engine_for
from tuimanji.engine import NotYourTurn
from tuimanji.games.tic_tac_toe import TicTacToe
from tuimanji.store import MatchNotReady


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIMANJI_DB", str(tmp_path))
    return engine_for("tic-tac-toe")


@pytest.fixture
def game() -> TicTacToe:
    return TicTacToe()


def _seat_and_start(engine, game, creator="alice", opponent="bob"):
    match_id = store.create_match(engine, game, creator)
    store.join_match(engine, game, match_id, opponent)
    store.start_match(engine, game, match_id, creator)
    return match_id


def test_wal_mode_enabled(engine):
    with engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert mode.lower() == "wal"


def test_join_does_not_auto_start(engine, game):
    match_id = store.create_match(engine, game, "alice")
    store.join_match(engine, game, match_id, "bob")
    assert store.latest_state(engine, match_id) is None
    m = store.get_match(engine, match_id)
    assert m is not None and m.status == "waiting"
    assert store.match_players(engine, match_id) == ["alice", "bob"]


def test_start_match_requires_creator(engine, game):
    match_id = store.create_match(engine, game, "alice")
    store.join_match(engine, game, match_id, "bob")
    with pytest.raises(ValueError, match="creator"):
        store.start_match(engine, game, match_id, "bob")
    store.start_match(engine, game, match_id, "alice")
    state_row = store.latest_state(engine, match_id)
    assert state_row is not None and state_row.turn == 0
    assert state_row.current == "alice"
    m = store.get_match(engine, match_id)
    assert m is not None and m.status == "active"


def test_start_match_needs_min_players(engine, game):
    match_id = store.create_match(engine, game, "alice")
    with pytest.raises(MatchNotReady):
        store.start_match(engine, game, match_id, "alice")


def test_submit_action_turn_progression(engine, game):
    match_id = _seat_and_start(engine, game)
    after = store.submit_action(engine, match_id, "alice", {"row": 0, "col": 0}, game)
    assert after.turn == 1
    assert after.current == "bob"
    assert after.state["board"][0][0] == "X"


def test_wrong_turn_rejected(engine, game):
    match_id = _seat_and_start(engine, game)
    with pytest.raises(NotYourTurn):
        store.submit_action(engine, match_id, "bob", {"row": 0, "col": 0}, game)


def test_terminal_flips_match_status(engine, game):
    match_id = _seat_and_start(engine, game)
    moves = [
        ("alice", 0, 0),
        ("bob", 1, 0),
        ("alice", 0, 1),
        ("bob", 1, 1),
        ("alice", 0, 2),
    ]
    for p, r, c in moves:
        store.submit_action(engine, match_id, p, {"row": r, "col": c}, game)
    matches = store.list_matches(engine)
    assert len(matches) == 1
    assert matches[0].status == "finished"
    latest = store.latest_state(engine, match_id)
    assert latest is not None and latest.winner == "alice"


def test_race_same_turn_one_wins(tmp_path, monkeypatch, game):
    monkeypatch.setenv("TUIMANJI_DB", str(tmp_path))
    # Two separate engines pointing at the same DB file — simulates two processes.
    e1 = engine_for("tic-tac-toe")
    e2 = engine_for("tic-tac-toe")
    match_id = store.create_match(e1, game, "alice")
    store.join_match(e1, game, match_id, "bob")
    store.start_match(e1, game, match_id, "alice")
    # Alice plays through e1; bob (wrong turn) tries through e2 on same turn.
    store.submit_action(e1, match_id, "alice", {"row": 0, "col": 0}, game)
    with pytest.raises(NotYourTurn):
        store.submit_action(e2, match_id, "alice", {"row": 1, "col": 1}, game)

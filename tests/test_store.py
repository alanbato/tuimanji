import pytest

from tuimanji import store
from tuimanji.db import engine_for
from tuimanji.engine import NotYourTurn
from tuimanji.games.tic_tac_toe import TicTacToe


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIMANJI_DB", str(tmp_path))
    return engine_for("tic-tac-toe")


@pytest.fixture
def game() -> TicTacToe:
    return TicTacToe()


def test_wal_mode_enabled(engine):
    with engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert mode.lower() == "wal"


def test_create_and_join_starts_match(engine, game):
    match_id = store.create_match(engine, game, "alice")
    assert store.latest_state(engine, match_id) is None
    store.join_match(engine, game, match_id, "bob")
    state_row = store.latest_state(engine, match_id)
    assert state_row is not None
    assert state_row.turn == 0
    assert state_row.current == "alice"
    assert store.match_players(engine, match_id) == ["alice", "bob"]


def test_submit_action_turn_progression(engine, game):
    match_id = store.create_match(engine, game, "alice")
    store.join_match(engine, game, match_id, "bob")
    after = store.submit_action(engine, match_id, "alice", {"row": 0, "col": 0}, game)
    assert after.turn == 1
    assert after.current == "bob"
    assert after.state["board"][0][0] == "X"


def test_wrong_turn_rejected(engine, game):
    match_id = store.create_match(engine, game, "alice")
    store.join_match(engine, game, match_id, "bob")
    with pytest.raises(NotYourTurn):
        store.submit_action(engine, match_id, "bob", {"row": 0, "col": 0}, game)


def test_terminal_flips_match_status(engine, game):
    match_id = store.create_match(engine, game, "alice")
    store.join_match(engine, game, match_id, "bob")
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
    # Alice plays through e1; bob (wrong turn) tries through e2 on same turn.
    store.submit_action(e1, match_id, "alice", {"row": 0, "col": 0}, game)
    with pytest.raises(NotYourTurn):
        store.submit_action(e2, match_id, "alice", {"row": 1, "col": 1}, game)

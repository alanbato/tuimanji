import pytest
from sqlmodel import Session

from tuimanji import store
from tuimanji.db import _make_engine, _reset_engine, get_engine
from tuimanji.engine import NotYourTurn
from tuimanji.games.connect4 import Connect4
from tuimanji.games.tic_tac_toe import TicTacToe
from tuimanji.models import MatchState
from tuimanji.store import MatchNotReady


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIMANJI_DB", str(tmp_path))
    _reset_engine()
    return get_engine()


@pytest.fixture
def game() -> TicTacToe:
    return TicTacToe()


def _seat_and_start(game, creator="alice", opponent="bob"):
    match_id = store.create_match(game, creator)
    store.join_match(game, match_id, opponent)
    store.start_match(game, match_id, creator)
    return match_id


def test_wal_mode_enabled(engine):
    with engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert mode.lower() == "wal"


def test_busy_timeout_set(engine):
    with engine.connect() as conn:
        timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
    assert timeout == 5000


def test_join_does_not_auto_start(engine, game):
    match_id = store.create_match(game, "alice")
    store.join_match(game, match_id, "bob")
    assert store.latest_state(match_id) is None
    m = store.get_match(match_id)
    assert m is not None and m.status == "waiting"
    assert store.match_players(match_id) == ["alice", "bob"]


def test_start_match_requires_creator(engine, game):
    match_id = store.create_match(game, "alice")
    store.join_match(game, match_id, "bob")
    with pytest.raises(ValueError, match="creator"):
        store.start_match(game, match_id, "bob")
    store.start_match(game, match_id, "alice")
    state_row = store.latest_state(match_id)
    assert state_row is not None and state_row.turn == 0
    assert state_row.current == "alice"
    m = store.get_match(match_id)
    assert m is not None and m.status == "active"


def test_start_match_needs_min_players(engine, game):
    match_id = store.create_match(game, "alice")
    with pytest.raises(MatchNotReady):
        store.start_match(game, match_id, "alice")


def test_submit_action_turn_progression(engine, game):
    match_id = _seat_and_start(game)
    after = store.submit_action(match_id, "alice", {"row": 0, "col": 0}, game)
    assert after.turn == 1
    assert after.current == "bob"
    assert after.state["board"][0][0] == "X"


def test_wrong_turn_rejected(engine, game):
    match_id = _seat_and_start(game)
    with pytest.raises(NotYourTurn):
        store.submit_action(match_id, "bob", {"row": 0, "col": 0}, game)


def test_terminal_flips_match_status(engine, game):
    match_id = _seat_and_start(game)
    moves = [
        ("alice", 0, 0),
        ("bob", 1, 0),
        ("alice", 0, 1),
        ("bob", 1, 1),
        ("alice", 0, 2),
    ]
    for p, r, c in moves:
        store.submit_action(match_id, p, {"row": r, "col": c}, game)
    matches = store.list_matches("tic-tac-toe")
    assert len(matches) == 1
    assert matches[0].status == "finished"
    latest = store.latest_state(match_id)
    assert latest is not None and latest.winner == "alice"


def test_race_same_turn_one_wins(tmp_path, monkeypatch, game):
    monkeypatch.setenv("TUIMANJI_DB", str(tmp_path))
    _reset_engine()
    # Two separate engines pointing at the same DB file — simulates two processes.
    e1 = _make_engine()
    e2 = _make_engine()  # noqa: F841 (kept for symmetry; store uses the singleton)
    match_id = store.create_match(game, "alice")
    store.join_match(game, match_id, "bob")
    store.start_match(game, match_id, "alice")
    # Alice plays; then tries again on what she thinks is still her turn.
    store.submit_action(match_id, "alice", {"row": 0, "col": 0}, game)
    with pytest.raises(NotYourTurn):
        store.submit_action(match_id, "alice", {"row": 1, "col": 1}, game)
    # Both engines still read the same DB file.
    with e1.connect() as conn:
        rows = conn.exec_driver_sql("SELECT COUNT(*) FROM matchstate").scalar()
    assert rows == 2  # turn 0 + turn 1


def test_match_counts_by_game(engine, game):
    alice_match = store.create_match(game, "alice")
    store.join_match(game, alice_match, "bob")
    store.start_match(game, alice_match, "alice")
    store.create_match(game, "carol")  # waiting
    store.create_match(Connect4(), "dave")  # different game
    counts = store.match_counts_by_game()
    assert counts["tic-tac-toe"] == (2, 0)
    assert counts["connect-4"] == (1, 0)


def test_match_ids_unique_across_games(engine, game):
    tt_ids = {store.create_match(game, f"alice{i}") for i in range(20)}
    c4_ids = {store.create_match(Connect4(), f"bob{i}") for i in range(20)}
    assert not (tt_ids & c4_ids), "match ids must be globally unique"


def test_find_match_game(engine, game):
    tt_match = store.create_match(game, "alice")
    c4_match = store.create_match(Connect4(), "bob")
    assert store.find_match_game(tt_match) == "tic-tac-toe"
    assert store.find_match_game(c4_match) == "connect-4"
    assert store.find_match_game("nope") is None


def test_best_resumable_picks_active_over_waiting(engine, game):
    waiting_id = store.create_match(game, "alice")
    active_id = _seat_and_start(game, creator="alice", opponent="bob")
    # Ignore the waiting one variable; it's intentionally left untouched.
    _ = waiting_id
    found = store.best_resumable("alice")
    assert found is not None
    game_id, match = found
    assert game_id == "tic-tac-toe"
    assert match.id == active_id
    assert match.status == "active"


def test_best_resumable_prefers_where_player_last_acted(engine, game):
    # Two active tic-tac-toe matches for alice. The second was created more
    # recently, but alice took her most recent turn in the FIRST one.
    older = _seat_and_start(game, creator="alice", opponent="bob")
    _ = _seat_and_start(game, creator="alice", opponent="carol")
    # Alice acts in `older` after `newer` was created → older's action_ts
    # exceeds newer's match.created_at.
    store.submit_action(older, "alice", {"row": 0, "col": 0}, game)
    found = store.best_resumable("alice")
    assert found is not None
    _, match = found
    assert match.id == older


def test_best_resumable_falls_back_to_match_created_at(engine, game, monkeypatch):
    # Both matches are freshly seated with no actions; fall back to created_at.
    # `_now` resolution is 1s, so fake the clock to get distinct timestamps.
    clock = iter([100, 100, 200, 200])
    monkeypatch.setattr(store, "_now", lambda: next(clock))
    first = _seat_and_start(game, creator="alice", opponent="bob")
    second = _seat_and_start(game, creator="alice", opponent="carol")
    found = store.best_resumable("alice")
    assert found is not None
    _, match = found
    assert match.id == second
    _ = first


def test_submit_action_converts_integrity_error_to_not_your_turn(engine, game):
    match_id = _seat_and_start(game)
    # Manually insert a colliding turn-1 MatchState so alice's submit trips
    # the (match_id, turn) unique constraint at commit time.
    with Session(get_engine()) as s:
        s.add(
            MatchState(
                match_id=match_id,
                turn=1,
                state={"stub": True},
                current="bob",
                winner=None,
                created_at=0,
            )
        )
        s.commit()
    with pytest.raises(NotYourTurn):
        store.submit_action(match_id, "alice", {"row": 0, "col": 0}, game)

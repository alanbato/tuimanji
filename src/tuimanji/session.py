import fcntl
import os
from pathlib import Path

from . import store
from .db import db_dir, engine_for
from .games import all_games

MAX_SLOTS = 16

_held_fd: int | None = None


def _sessions_dir(user: str) -> Path:
    d = db_dir() / ".sessions" / user
    d.mkdir(parents=True, exist_ok=True)
    return d


def _try_lock(path: Path) -> int | None:
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def player_id_for(user: str, slot: int) -> str:
    return user if slot == 0 else f"{user}#{slot + 1}"


def _parse_slot(user: str, player_id: str) -> int | None:
    if player_id == user:
        return 0
    prefix = f"{user}#"
    if not player_id.startswith(prefix):
        return None
    try:
        return int(player_id[len(prefix) :]) - 1
    except ValueError:
        return None


def find_resume_target(player_id: str) -> tuple[str, str, str] | None:
    """Return `(game_id, match_id, status)` for the match `player_id` should
    resume, or None if there isn't one. Prefers active matches over waiting
    ones, newest first within each bucket.
    """
    candidates = (
        (game.id, m)
        for game in all_games()
        if (m := store.best_resumable(engine_for(game.id), player_id)) is not None
    )
    best = min(
        candidates,
        key=lambda gm: (gm[1].status != "active", -gm[1].created_at),
        default=None,
    )
    if best is None:
        return None
    game_id, m = best
    return game_id, m.id, m.status


def _resumable_slots(user: str) -> list[int]:
    slots: set[int] = set()
    for game in all_games():
        engine = engine_for(game.id)
        for m in store.list_matches(engine):
            if m.status == "finished":
                continue
            for pid in store.match_players(engine, m.id):
                slot = _parse_slot(user, pid)
                if slot is not None and 0 <= slot < MAX_SLOTS:
                    slots.add(slot)
    return sorted(slots)


def acquire(user: str) -> tuple[int, str]:
    """Claim the lowest-free session slot for `user`, preferring slots that
    have an unfinished match seated for that identity (so relaunches resume
    their prior seat). Returns (slot, player_id). The flock is held for the
    lifetime of this process.
    """
    global _held_fd
    sdir = _sessions_dir(user)
    preferred = _resumable_slots(user)
    seen: set[int] = set()
    order = preferred + [s for s in range(MAX_SLOTS) if s not in preferred]
    for slot in order:
        if slot in seen:
            continue
        seen.add(slot)
        fd = _try_lock(sdir / f"{slot}.lock")
        if fd is not None:
            _held_fd = fd
            return slot, player_id_for(user, slot)
    raise RuntimeError(f"no free session slot (max {MAX_SLOTS})")

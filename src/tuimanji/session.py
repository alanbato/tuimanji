"""Session slots — per-process identity keyed off unix user.

Two terminals logged in as the same unix user get *distinct* player ids by
claiming different slots: slot 0 is bare ``user``, slot ≥1 is
``user#{slot+1}``. Each slot is guarded by an ``flock`` on
``$TUIMANJI_DB/.sessions/<user>/<N>.lock``; the lock is held for process
lifetime and released by the OS on exit (including crash).

:func:`acquire` prefers slots that already have a seat in an unfinished
match, so a crashed process relaunches into its old identity and can
rejoin its seat rather than claiming a fresh one.
"""

import fcntl
import os
from pathlib import Path

from sqlmodel import Session, col, select

from . import store
from .db import db_dir, get_engine
from .models import Match, MatchPlayer

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
    found = store.best_resumable(player_id)
    if found is None:
        return None
    game_id, match = found
    return game_id, match.id, match.status


def _resumable_slots(user: str) -> list[int]:
    prefix = f"{user}#"
    with Session(get_engine()) as s:
        stmt = (
            select(MatchPlayer.player_id)
            .join(Match, col(Match.id) == col(MatchPlayer.match_id))
            .where(col(Match.status) != "finished")
            .where(
                (col(MatchPlayer.player_id) == user)
                | col(MatchPlayer.player_id).startswith(prefix)
            )
            .distinct()
        )
        slots: set[int] = set()
        for (pid,) in s.execute(stmt):
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

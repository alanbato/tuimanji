"""``tuimanji doctor`` — diagnose pubnix permission issues.

The store is a single SQLite file plus its WAL/SHM sidecars under
``$TUIMANJI_DB``, with per-user lock files under ``.sessions/<user>/``.
On a shared host, SQLite's ``attempt to write a readonly database`` almost
always traces to one of those paths being owned by a different user with
restrictive perms — the most common case is a DB created before the data
dir was set to ``1777``, which leaves later users unable to write to it.

This module walks every relevant path, reports owner / mode / write access
for the running user, attempts a real write against the DB, and prints
exact ``chmod`` commands for whatever is wrong. It's read-only — diagnosis
only — so it's safe for any user to run.
"""

from __future__ import annotations

import os
import pwd
import stat
from collections.abc import Callable
from pathlib import Path

from sqlmodel import Session, select

from .db import db_dir, db_path, get_engine, is_shared_dir
from .identity import current_player
from .models import Match


def _owner(path: Path) -> str:
    try:
        uid = path.stat().st_uid
    except OSError:
        return "?"
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return f"uid={uid}"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _writable(path: Path) -> bool:
    return os.access(path, os.W_OK)


def _fmt_mode(m: int) -> str:
    sticky = "t" if m & 0o1000 else ""
    return f"{m:04o}{(' (' + sticky + ')') if sticky else ''}"


def _line(echo: Callable[[str], None], path: Path, *, want: str) -> tuple[str, bool]:
    if not path.exists():
        echo(f"  {path}  [missing]")
        return f"{path} missing", False
    m = _mode(path)
    owner = _owner(path)
    writable = _writable(path)
    flag = "ok" if writable else "NOT writable"
    echo(f"  {path}  mode={_fmt_mode(m)} owner={owner}  ({flag})")
    return f"{path} ({want})", writable


def run_doctor(echo: Callable[[str], None]) -> int:
    """Print a diagnostic report. Returns exit code 0 if everything looks
    writable to the current user, 1 otherwise."""
    user = current_player()
    base = db_dir()
    echo(f"tuimanji doctor — running as {user}")
    echo(f"data dir: {base}")
    echo("")

    problems: list[str] = []

    echo("[directories]")
    label, ok = _line(echo, base, want="1777")
    if not ok or not is_shared_dir(base):
        if not is_shared_dir(base):
            problems.append(f"data dir not sticky+world-writable — chmod 1777 {base}")
    sessions = base / ".sessions"
    if sessions.exists():
        _line(echo, sessions, want="1777")
        if not is_shared_dir(sessions):
            problems.append(
                f".sessions/ not sticky+world-writable — chmod 1777 {sessions}"
            )
    user_sessions = sessions / user
    if user_sessions.exists():
        _line(echo, user_sessions, want="user-private")

    echo("")
    echo("[database files]")
    db_files = [
        db_path(),
        base / "tuimanji.db-wal",
        base / "tuimanji.db-shm",
    ]
    db_unwritable: list[Path] = []
    for p in db_files:
        if p.exists():
            _, ok = _line(echo, p, want="0666")
            if not ok:
                db_unwritable.append(p)

    if db_unwritable:
        joined = " ".join(str(p) for p in db_unwritable)
        problems.append(f"db files not writable — chmod 666 {joined}")

    echo("")
    echo("[write probe]")
    try:
        with Session(get_engine()) as s:
            s.execute(select(Match).limit(1))
            s.commit()
        echo("  read+commit succeeded")
    except Exception as e:
        echo(f"  FAILED: {type(e).__name__}: {e}")
        problems.append(f"write probe failed: {e}")

    echo("")
    if not problems:
        echo("All paths look writable. If users still hit errors, check that")
        echo("the directory chain to the data dir is traversable (x-bit) for")
        echo("everyone, and that the filesystem isn't mounted read-only.")
        return 0

    echo("Problems found — run as root (or as the file owner) to fix:")
    for p in problems:
        echo(f"  - {p}")
    return 1

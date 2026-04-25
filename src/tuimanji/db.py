"""SQLite engine bootstrap.

One engine per process, keyed off ``$TUIMANJI_DB`` (default
``/var/games/tuimanji``). WAL mode, 5s busy timeout, and
``BEGIN IMMEDIATE`` on every transaction — see :mod:`tuimanji.store` for
why the last one matters.
"""

import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

from . import models  # noqa: F401  (register tables with metadata)

DEFAULT_DB_DIR = Path("/var/games/tuimanji")

_engine: Engine | None = None


def is_shared_dir(path: Path) -> bool:
    """True if `path` is set up for multi-user (pubnix) sharing — sticky bit
    plus world-writable, like ``/tmp``. The admin opts in by ``chmod 1777``-ing
    the data dir; the code then propagates ``1777``/``0o666`` to subdirs and
    files it creates inside, so users on a shared host don't trip on each
    other's umask. A non-shared dir (e.g. a personal ``~/.local/share``)
    stays untouched."""
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return bool(mode & 0o1000) and bool(mode & 0o002)


def propagate_shared_perms(child: Path, parent: Path) -> None:
    """If `parent` is a shared dir, chmod `child` to match (``1777`` for
    dirs, ``0o666`` for files). Best-effort: silently skips on EPERM, since
    files we don't own were placed there by someone else who knows better."""
    if not is_shared_dir(parent):
        return
    try:
        mode = 0o1777 if child.is_dir() else 0o666
        os.chmod(child, mode)
    except OSError:
        pass


def db_dir() -> Path:
    """Return the directory holding ``tuimanji.db``, creating it if missing."""
    raw = os.environ.get("TUIMANJI_DB")
    path = Path(raw) if raw else DEFAULT_DB_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    """Return the path to ``tuimanji.db`` inside :func:`db_dir`."""
    return db_dir() / "tuimanji.db"


def _share_db_files(parent: Path) -> None:
    """If `parent` is shared, chmod tuimanji.db and any WAL/shm sidecars to
    ``0o666`` so other users on the box can write. Sidecars are created
    lazily by SQLite, so this gets called both at engine init and on every
    new connection."""
    if not is_shared_dir(parent):
        return
    for name in ("tuimanji.db", "tuimanji.db-wal", "tuimanji.db-shm"):
        p = parent / name
        if p.exists():
            try:
                os.chmod(p, 0o666)
            except OSError:
                pass


def _make_engine() -> Engine:
    """Build a fresh engine, bypassing the module singleton. Used by tests
    that need two independent engines pointing at the same file to simulate
    two processes."""
    engine = create_engine(
        f"sqlite:///{db_path()}",
        connect_args={"check_same_thread": False},
    )

    parent = db_dir()

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()
        # WAL/shm sidecars are created lazily by SQLite on the first WAL
        # write; on a shared host they need to be world-writable so other
        # users can read/write them too.
        _share_db_files(parent)

    @event.listens_for(engine, "begin")
    def _begin_immediate(conn):
        # SQLAlchemy's default DEFERRED transactions can hit SQLITE_BUSY_SNAPSHOT
        # on shared→reserved lock upgrades, which busy_timeout does not retry.
        # Starting every transaction as IMMEDIATE takes the reserved lock up
        # front so contenders wait cleanly on busy_timeout instead.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    SQLModel.metadata.create_all(engine)
    _share_db_files(parent)
    return engine


def get_engine() -> Engine:
    """Return the cached module-level engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def _reset_engine() -> None:
    """Test-only: drop the cached singleton so the next get_engine() picks up
    a new TUIMANJI_DB (typically a per-test tmp_path)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None

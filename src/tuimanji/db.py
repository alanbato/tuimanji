import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

from . import models  # noqa: F401  (register tables with metadata)

DEFAULT_DB_DIR = Path("/var/games/tuimanji")

_engine: Engine | None = None


def db_dir() -> Path:
    raw = os.environ.get("TUIMANJI_DB")
    path = Path(raw) if raw else DEFAULT_DB_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return db_dir() / "tuimanji.db"


def _make_engine() -> Engine:
    """Build a fresh engine, bypassing the module singleton. Used by tests
    that need two independent engines pointing at the same file to simulate
    two processes."""
    engine = create_engine(
        f"sqlite:///{db_path()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    @event.listens_for(engine, "begin")
    def _begin_immediate(conn):
        # SQLAlchemy's default DEFERRED transactions can hit SQLITE_BUSY_SNAPSHOT
        # on shared→reserved lock upgrades, which busy_timeout does not retry.
        # Starting every transaction as IMMEDIATE takes the reserved lock up
        # front so contenders wait cleanly on busy_timeout instead.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    SQLModel.metadata.create_all(engine)
    return engine


def get_engine() -> Engine:
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

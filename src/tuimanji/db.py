import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

from . import models  # noqa: F401  (register tables with metadata)

DEFAULT_DB_DIR = Path("/var/games/tuimanji")


def db_dir() -> Path:
    raw = os.environ.get("TUIMANJI_DB")
    path = Path(raw) if raw else DEFAULT_DB_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path(game_id: str) -> Path:
    return db_dir() / f"{game_id}.db"


def engine_for(game_id: str) -> Engine:
    path = db_path(game_id)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SQLModel.metadata.create_all(engine)
    return engine

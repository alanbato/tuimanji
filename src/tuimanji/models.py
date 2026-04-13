from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class Match(SQLModel, table=True):
    id: str = Field(primary_key=True)
    game_id: str = Field(index=True)
    created_by: str
    created_at: int
    status: str  # "waiting" | "active" | "finished"
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class MatchPlayer(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("match_id", "player_id"),)

    match_id: str = Field(primary_key=True, foreign_key="match.id")
    seat: int = Field(primary_key=True)
    player_id: str = Field(index=True)


class MatchState(SQLModel, table=True):
    match_id: str = Field(primary_key=True, foreign_key="match.id")
    turn: int = Field(primary_key=True)
    state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    current: str | None = None
    winner: str | None = None
    created_at: int


class Action(SQLModel, table=True):
    match_id: str = Field(primary_key=True, foreign_key="match.id")
    turn: int = Field(primary_key=True)
    player_id: str
    action: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: int

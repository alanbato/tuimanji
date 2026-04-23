"""SQLModel tables backing the shared SQLite database.

Two of these (:class:`MatchState`, :class:`Action`) are append-only — never
updated. :class:`Match` mutates only its ``status`` column (``waiting →
active → finished``); seats and config are fixed at creation time. See
:mod:`tuimanji.store` for the enforcement.
"""

from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class Match(SQLModel, table=True):
    """A scheduled or in-flight match. Status advances; nothing else mutates."""

    id: str = Field(primary_key=True)
    game_id: str = Field(index=True)
    created_by: str
    created_at: int
    status: str  # "waiting" | "active" | "finished"
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class MatchPlayer(SQLModel, table=True):
    """A seat assignment. Insert-only — seats aren't re-ordered or swapped."""

    __table_args__ = (UniqueConstraint("match_id", "player_id"),)

    match_id: str = Field(primary_key=True, foreign_key="match.id")
    seat: int = Field(primary_key=True)
    player_id: str = Field(index=True)


class MatchState(SQLModel, table=True):
    """Append-only snapshot of game state at a given turn.

    The composite ``(match_id, turn)`` primary key is what protects
    :func:`tuimanji.store.submit_action` against same-player double-submits:
    two writers both passing the ``current == player`` check will race on
    insert and the loser surfaces as :class:`NotYourTurn`.
    """

    match_id: str = Field(primary_key=True, foreign_key="match.id")
    turn: int = Field(primary_key=True)
    state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    current: str | None = None
    winner: str | None = None
    created_at: int


class Action(SQLModel, table=True):
    """Append-only log of every submitted action. One row per turn.

    Paired 1:1 with :class:`MatchState` turns ≥ 1 (turn 0 has no action —
    it's the initial state written by :func:`tuimanji.store.start_match`).
    """

    match_id: str = Field(primary_key=True, foreign_key="match.id")
    turn: int = Field(primary_key=True)
    player_id: str
    action: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: int

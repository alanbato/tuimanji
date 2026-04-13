import time
import uuid

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from .engine import Game, MatchNotFound, NotYourTurn
from .models import Action, Match, MatchPlayer, MatchState


def _now() -> int:
    return int(time.time())


def create_match(engine: Engine, game: Game, creator: str) -> str:
    match_id = uuid.uuid4().hex[:12]
    with Session(engine) as s:
        s.add(
            Match(
                id=match_id,
                game_id=game.id,
                created_by=creator,
                created_at=_now(),
                status="waiting",
                config={
                    "min_players": game.min_players,
                    "max_players": game.max_players,
                },
            )
        )
        s.add(MatchPlayer(match_id=match_id, seat=0, player_id=creator))
        s.commit()
    return match_id


def join_match(engine: Engine, game: Game, match_id: str, player: str) -> None:
    with Session(engine) as s:
        match = s.get(Match, match_id)
        if match is None:
            raise MatchNotFound(match_id)
        seats = list(
            s.scalars(
                select(MatchPlayer)
                .where(MatchPlayer.match_id == match_id)
                .order_by(col(MatchPlayer.seat))
            )
        )
        if any(mp.player_id == player for mp in seats):
            return  # already joined
        if match.status != "waiting":
            raise ValueError(f"match {match_id} is not accepting players")
        next_seat = len(seats)
        if next_seat >= game.max_players:
            raise ValueError("match is full")
        s.add(MatchPlayer(match_id=match_id, seat=next_seat, player_id=player))
        seats_after = [mp.player_id for mp in seats] + [player]
        if len(seats_after) >= game.min_players:
            initial = game.initial_state(seats_after)
            match.status = "active"
            s.add(
                MatchState(
                    match_id=match_id,
                    turn=0,
                    state=initial,
                    current=game.current_player(initial),
                    winner=game.winner(initial),
                    created_at=_now(),
                )
            )
        s.commit()


def latest_state(engine: Engine, match_id: str) -> MatchState | None:
    with Session(engine) as s:
        stmt = (
            select(MatchState)
            .where(MatchState.match_id == match_id)
            .order_by(col(MatchState.turn).desc())
            .limit(1)
        )
        return s.scalars(stmt).first()


def list_matches(engine: Engine, status: str | None = None) -> list[Match]:
    with Session(engine) as s:
        stmt = select(Match).order_by(col(Match.created_at).desc())
        if status is not None:
            stmt = stmt.where(Match.status == status)
        return list(s.scalars(stmt))


def match_players(engine: Engine, match_id: str) -> list[str]:
    with Session(engine) as s:
        stmt = (
            select(MatchPlayer)
            .where(MatchPlayer.match_id == match_id)
            .order_by(col(MatchPlayer.seat))
        )
        return [mp.player_id for mp in s.scalars(stmt)]


def submit_action(
    engine: Engine, match_id: str, player: str, action: dict, game: Game
) -> MatchState:
    with Session(engine) as s:
        latest = s.scalars(
            select(MatchState)
            .where(MatchState.match_id == match_id)
            .order_by(col(MatchState.turn).desc())
            .limit(1)
        ).first()
        if latest is None:
            raise MatchNotFound(match_id)
        if latest.current != player:
            raise NotYourTurn(player, latest.current)

        new_state_data = game.apply_action(latest.state, player, action)
        next_turn = latest.turn + 1
        now = _now()
        s.add(
            Action(
                match_id=match_id,
                turn=next_turn,
                player_id=player,
                action=action,
                created_at=now,
            )
        )
        new_row = MatchState(
            match_id=match_id,
            turn=next_turn,
            state=new_state_data,
            current=game.current_player(new_state_data),
            winner=game.winner(new_state_data),
            created_at=now,
        )
        s.add(new_row)
        if game.is_terminal(new_state_data):
            match = s.get(Match, match_id)
            if match is not None:
                match.status = "finished"
        s.commit()
        s.refresh(new_row)
        return new_row

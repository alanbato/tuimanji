import time
import uuid

from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from .db import get_engine
from .engine import Game, MatchNotFound, NotYourTurn
from .models import Action, Match, MatchPlayer, MatchState


def _now() -> int:
    return int(time.time())


def create_match(game: Game, creator: str) -> str:
    match_id = uuid.uuid4().hex[:10]
    with Session(get_engine()) as s:
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


def join_match(game: Game, match_id: str, player: str) -> None:
    with Session(get_engine()) as s:
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
        s.commit()


class MatchNotReady(Exception):
    pass


def start_match(game: Game, match_id: str, player: str) -> None:
    """Transition a waiting match to active. Only the creator may start, and
    only once min_players seats are filled."""
    with Session(get_engine()) as s:
        match = s.get(Match, match_id)
        if match is None:
            raise MatchNotFound(match_id)
        if match.status != "waiting":
            raise ValueError(f"match {match_id} is not in waiting state")
        if match.created_by != player:
            raise ValueError("only the match creator can start the game")
        seats = list(
            s.scalars(
                select(MatchPlayer)
                .where(MatchPlayer.match_id == match_id)
                .order_by(col(MatchPlayer.seat))
            )
        )
        players = [mp.player_id for mp in seats]
        if len(players) < game.min_players:
            raise MatchNotReady(
                f"need at least {game.min_players} players, have {len(players)}"
            )
        initial = game.initial_state(players)
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


def get_match(match_id: str) -> Match | None:
    with Session(get_engine()) as s:
        return s.get(Match, match_id)


def latest_state(match_id: str) -> MatchState | None:
    with Session(get_engine()) as s:
        stmt = (
            select(MatchState)
            .where(MatchState.match_id == match_id)
            .order_by(col(MatchState.turn).desc())
            .limit(1)
        )
        return s.scalars(stmt).first()


def list_matches(game_id: str, status: str | None = None) -> list[Match]:
    with Session(get_engine()) as s:
        stmt = (
            select(Match)
            .where(col(Match.game_id) == game_id)
            .order_by(col(Match.created_at).desc())
        )
        if status is not None:
            stmt = stmt.where(col(Match.status) == status)
        return list(s.scalars(stmt))


def match_counts_by_game() -> dict[str, tuple[int, int]]:
    """Return `{game_id: (live, done)}` for every game that has at least one
    match. Callers should default missing games to (0, 0)."""
    with Session(get_engine()) as s:
        stmt = select(
            Match.game_id,
            Match.status,
            func.count().label("n"),
        ).group_by(col(Match.game_id), col(Match.status))
        counts: dict[str, tuple[int, int]] = {}
        for game_id, status, n in s.execute(stmt):
            live, done = counts.get(game_id, (0, 0))
            if status == "finished":
                done += int(n)
            else:
                live += int(n)
            counts[game_id] = (live, done)
        return counts


def best_resumable(player_id: str) -> tuple[str, Match] | None:
    """Return `(game_id, match)` for the single match `player_id` should
    resume across all games, or None. Active before waiting; within each
    bucket, the match where the player most recently took a turn wins, with
    `match.created_at` as a fallback for matches where they haven't acted
    yet (so freshly-joined waiting rooms still surface).
    """
    with Session(get_engine()) as s:
        priority = case((col(Match.status) == "active", 0), else_=1)
        # Most-recent action timestamp for this player, per match.
        last_action = (
            select(
                col(Action.match_id).label("mid"),
                func.max(col(Action.created_at)).label("last_ts"),
            )
            .where(col(Action.player_id) == player_id)
            .group_by(col(Action.match_id))
            .subquery()
        )
        engaged = func.coalesce(last_action.c.last_ts, col(Match.created_at))
        stmt = (
            select(Match)
            .join(MatchPlayer, col(MatchPlayer.match_id) == col(Match.id))
            .outerjoin(last_action, last_action.c.mid == col(Match.id))
            .where(col(MatchPlayer.player_id) == player_id)
            .where(col(Match.status) != "finished")
            .order_by(priority, engaged.desc())
            .limit(1)
        )
        match = s.scalars(stmt).first()
        if match is None:
            return None
        return match.game_id, match


def find_match_game(match_id: str) -> str | None:
    """Return the `game_id` of the match with this id, or None."""
    with Session(get_engine()) as s:
        match = s.get(Match, match_id)
        return match.game_id if match is not None else None


def match_players(match_id: str) -> list[str]:
    with Session(get_engine()) as s:
        stmt = (
            select(MatchPlayer)
            .where(MatchPlayer.match_id == match_id)
            .order_by(col(MatchPlayer.seat))
        )
        return [mp.player_id for mp in s.scalars(stmt)]


def submit_action(match_id: str, player: str, action: dict, game: Game) -> MatchState:
    with Session(get_engine()) as s:
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
        try:
            s.commit()
        except IntegrityError:
            # Lost the `(match_id, turn)` unique-constraint race against
            # another writer. Re-read latest and surface NotYourTurn so the
            # UI's existing handler takes over instead of a raw SQL error.
            s.rollback()
            latest_after = s.scalars(
                select(MatchState)
                .where(MatchState.match_id == match_id)
                .order_by(col(MatchState.turn).desc())
                .limit(1)
            ).first()
            raise NotYourTurn(
                player, latest_after.current if latest_after else None
            ) from None
        s.refresh(new_row)
        return new_row

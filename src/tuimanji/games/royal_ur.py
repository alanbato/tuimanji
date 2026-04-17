"""The Royal Game of Ur — Finkel rules.

Each turn is two committed actions: a roll, then a move (or pass when no piece
can use the roll). This mirrors Battleship's `phase` field: `apply_action`
dispatches on `state["phase"] in {"roll", "move"}`. Landing on a rosette keeps
`turn_player` the same and resets phase to "roll" for an extra turn — the same
"same player goes again" pattern Checkers uses for `continue_from`.

Dice randomness is computed inside `apply_action` and baked into the returned
state, exactly as Crazy Eights does for shuffles. Spectators and the opponent
read the result from `MatchState.state` via the standard 0.5s poll.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import bg_style, style
from ._common import (
    cursor_palette,
    header_palette,
    opponent_of,
    status_strip,
)

NUM_PIECES = 7
POOL = 0
HOME = 15
TRACK_LEN = 14  # squares 1..14 on the board

# Track index → (board_row, board_col), or None for off-board sentinels.
# Both players walk an L-shaped 14-square path; squares 5..12 are shared.
P1_TRACK: list[tuple[int, int] | None] = [
    None,
    (0, 3),
    (0, 2),
    (0, 1),
    (0, 0),  # 1..4 own entry lane (4 = rosette)
    (1, 0),
    (1, 1),
    (1, 2),
    (1, 3),  # 5..8 shared lane (8 = rosette)
    (1, 4),
    (1, 5),
    (1, 6),
    (1, 7),  # 9..12 shared lane
    (0, 7),
    (0, 6),  # 13..14 own exit lane (14 = rosette)
    None,
]
P2_TRACK: list[tuple[int, int] | None] = [
    None,
    (2, 3),
    (2, 2),
    (2, 1),
    (2, 0),
    (1, 0),
    (1, 1),
    (1, 2),
    (1, 3),
    (1, 4),
    (1, 5),
    (1, 6),
    (1, 7),
    (2, 7),
    (2, 6),
    None,
]

# Track indices that are rosettes for any player.
ROSETTES: frozenset[int] = frozenset({4, 8, 14})
# Squares walked by both players (capture possible here, except on rosette 8).
SHARED: frozenset[int] = frozenset(range(5, 13))

# Glyphs shared by render and animation overlays.
GLYPH = {0: "●", 1: "○"}  # by seat index
ROSETTE_GLYPH = "✦"

# Board cells that are rosettes — derived once from the canonical track tables.
_ROSETTE_CELLS: frozenset[tuple[int, int]] = frozenset(
    xy
    for track in (P1_TRACK, P2_TRACK)
    for i in ROSETTES
    if (xy := track[i]) is not None
)

# Pre-rendered box-drawing rows. The 3×8 board has gaps at row-0/row-2 cols 4,5.
TOP_BORDER = "┌───┬───┬───┬───┐       ┌───┬───┐"
SEP_R0_R1 = "├───┼───┼───┼───┼───┬───┼───┼───┤"
SEP_R1_R2 = "├───┼───┼───┼───┼───┴───┼───┼───┤"
BOT_BORDER = "└───┴───┴───┴───┘       └───┴───┘"

ROW_PRESENT = {
    0: (0, 1, 2, 3, 6, 7),
    1: (0, 1, 2, 3, 4, 5, 6, 7),
    2: (0, 1, 2, 3, 6, 7),
}


def _track_for(seat: int) -> list[tuple[int, int] | None]:
    return P1_TRACK if seat == 0 else P2_TRACK


def _xy(seat: int, pos: int) -> tuple[int, int] | None:
    return _track_for(seat)[pos]


def _seat_of(state: dict[str, Any], player: str) -> int:
    return state["order"].index(player)


def _occupied_by_self(state: dict[str, Any], player: str, target: int) -> bool:
    return target != HOME and target != POOL and target in state["pieces"][player]


def _opponent_index_at(
    state: dict[str, Any], opponent: str, opp_seat: int, target: int
) -> int | None:
    """Return the opponent's piece-index whose track position maps to the same
    board cell as `target` for the moving player, or None if no clash.

    Only relevant on shared squares; on private lanes the players' tracks map
    to disjoint cells, so an opponent piece value of `target` would land at a
    different (row, col).
    """
    if target not in SHARED:
        return None
    opp_pieces = state["pieces"][opponent]
    for idx, pos in enumerate(opp_pieces):
        if pos in SHARED and _xy(opp_seat, pos) == _xy(1 - opp_seat, target):
            return idx
    return None


def _legal_pieces(state: dict[str, Any], player: str, dice_sum: int) -> list[int]:
    """Indices of pieces the current player can move with `dice_sum` steps."""
    if dice_sum <= 0:
        return []
    seat = _seat_of(state, player)
    opponent = opponent_of(state["order"], player)
    opp_seat = 1 - seat
    pieces = state["pieces"][player]
    legal: list[int] = []
    for idx, pos in enumerate(pieces):
        if pos == HOME:
            continue
        target = pos + dice_sum
        if target > HOME:
            continue
        if target == HOME:
            legal.append(idx)
            continue
        if _occupied_by_self(state, player, target):
            continue
        if target == 8:  # central rosette is safe — can't land if opponent there
            opp_idx = _opponent_index_at(state, opponent, opp_seat, target)
            if opp_idx is not None:
                continue
        legal.append(idx)
    return legal


def _cursor_choices(state: dict[str, Any], player: str, dice_sum: int) -> list[int]:
    """Cursor-visible move choices: pool pieces collapse to one representative
    (they're interchangeable off-board), board pieces remain individual."""
    pieces = state["pieces"][player]
    pool_rep: int | None = None
    board: list[int] = []
    for idx in _legal_pieces(state, player, dice_sum):
        if pieces[idx] == POOL:
            if pool_rep is None:
                pool_rep = idx
        else:
            board.append(idx)
    return ([pool_rep] if pool_rep is not None else []) + board


def _roll_dice() -> list[int]:
    return [random.randint(0, 1) for _ in range(4)]


def _clone_pieces(state: dict[str, Any]) -> dict[str, list[int]]:
    """Deep-copy `pieces` so writers never alias the prev_state's inner lists.

    `MatchState` rows are append-only; aliasing the same `list[int]` between
    two `MatchState.state` dicts would let a later mutation silently corrupt
    a prior turn's snapshot.
    """
    return {p: list(positions) for p, positions in state["pieces"].items()}


# ---------- animations ----------


@dataclass
class _DiceAnimation:
    final: list[int]
    spins: list[list[int]]
    interval: float = 0.06

    @property
    def frames(self) -> int:
        return len(self.spins) + 1

    def overlay(self, frame: int) -> dict[str, Any]:
        if frame < len(self.spins):
            values = self.spins[frame]
        else:
            values = self.final
        return {
            "kind": "dice",
            "values": list(values),
            "sum": sum(self.final),
            "settled": frame >= len(self.spins),
        }


@dataclass
class _MoveAnimation:
    player: str
    seat: int
    piece_idx: int
    glyph: str
    path_xy: list[tuple[int, int] | None]  # one entry per intermediate frame
    capture_xy: tuple[int, int] | None
    capture_glyph: str | None
    interval: float = 0.08
    flash_frames: int = 3

    @property
    def frames(self) -> int:
        n = len(self.path_xy)
        return n + (self.flash_frames if self.capture_xy is not None else 0)

    def overlay(self, frame: int) -> dict[str, Any]:
        path_n = len(self.path_xy)
        if frame < path_n:
            xy = self.path_xy[frame]
            return {
                "kind": "move",
                "player": self.player,
                "piece_idx": self.piece_idx,
                "glyph": self.glyph,
                "xy": list(xy) if xy is not None else None,
                "capture_xy": list(self.capture_xy) if self.capture_xy else None,
                "capture_glyph": self.capture_glyph,
                "capture_visible": True,
            }
        flash_idx = frame - path_n
        return {
            "kind": "move",
            "player": self.player,
            "piece_idx": self.piece_idx,
            "glyph": self.glyph,
            "xy": list(self.path_xy[-1]) if self.path_xy[-1] is not None else None,
            "capture_xy": list(self.capture_xy) if self.capture_xy else None,
            "capture_glyph": self.capture_glyph,
            "capture_visible": flash_idx % 2 == 1,
        }


# ---------- the game ----------


class RoyalUr:
    id = "royal-ur"
    name = "Royal Game of Ur"
    min_players = 2
    max_players = 2

    # ---------- lifecycle ----------

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 2:
            raise ValueError("royal-ur requires exactly 2 players")
        p1, p2 = players
        return {
            "order": [p1, p2],
            "marks": {p1: GLYPH[0], p2: GLYPH[1]},
            "turn_player": p1,
            "phase": "roll",
            "dice": None,
            "pieces": {p1: [POOL] * NUM_PIECES, p2: [POOL] * NUM_PIECES},
            "scored": {p1: 0, p2: 0},
            "winner": None,
            "last_roll": None,
            "last_move": None,
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if state.get("winner") is not None:
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")
        atype = action.get("type")
        phase = state["phase"]
        if phase == "roll":
            if atype != "roll":
                raise IllegalAction(f"expected roll, got {atype}")
            return self._apply_roll(state, player)
        if phase == "move":
            if atype == "move":
                return self._apply_move(state, player, action)
            if atype == "pass":
                return self._apply_pass(state, player)
            raise IllegalAction(f"expected move or pass, got {atype}")
        raise IllegalAction(f"unknown phase: {phase}")

    # ---------- action handlers ----------

    def _apply_roll(self, state: dict[str, Any], player: str) -> dict[str, Any]:
        dice = _roll_dice()
        total = sum(dice)
        new_state: dict[str, Any] = {
            **state,
            "pieces": _clone_pieces(state),
            "scored": dict(state["scored"]),
            "dice": dice,
            "last_roll": {"player": player, "dice": list(dice), "sum": total},
            "last_move": None,
        }
        if total == 0:
            new_state["phase"] = "roll"
            new_state["turn_player"] = opponent_of(state["order"], player)
            new_state["dice"] = None
        else:
            new_state["phase"] = "move"
        return new_state

    def _apply_move(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        dice = state.get("dice")
        if not dice:
            raise IllegalAction("must roll before moving")
        try:
            idx = int(action["piece_idx"])
        except (KeyError, TypeError, ValueError) as e:
            raise IllegalAction(f"bad move action: {action}") from e
        if not (0 <= idx < NUM_PIECES):
            raise IllegalAction(f"piece_idx out of range: {idx}")

        seat = _seat_of(state, player)
        opponent = opponent_of(state["order"], player)
        opp_seat = 1 - seat
        dice_sum = sum(dice)
        legal = _legal_pieces(state, player, dice_sum)
        if idx not in legal:
            raise IllegalAction(f"piece {idx} cannot move {dice_sum}")

        from_pos = state["pieces"][player][idx]
        to_pos = from_pos + dice_sum

        new_pieces = _clone_pieces(state)
        new_pieces[player][idx] = to_pos

        captured_idx: int | None = None
        if to_pos != HOME and to_pos in SHARED and to_pos != 8:
            captured_idx = _opponent_index_at(state, opponent, opp_seat, to_pos)
            if captured_idx is not None:
                new_pieces[opponent][captured_idx] = POOL

        new_scored = dict(state["scored"])
        if to_pos == HOME:
            new_scored[player] = new_scored[player] + 1

        winner = player if new_scored[player] == NUM_PIECES else None
        landed_rosette = to_pos in ROSETTES and to_pos != HOME
        next_phase = "roll"
        if winner is not None:
            next_player = player
        elif landed_rosette:
            next_player = player
        else:
            next_player = opponent

        return {
            **state,
            "pieces": new_pieces,
            "scored": new_scored,
            "phase": next_phase,
            "dice": None,
            "turn_player": next_player,
            "winner": winner,
            "last_roll": None,
            "last_move": {
                "player": player,
                "piece_idx": idx,
                "from": from_pos,
                "to": to_pos,
                "captured_player": opponent if captured_idx is not None else None,
                "captured_idx": captured_idx,
                "rosette": landed_rosette,
            },
        }

    def _apply_pass(self, state: dict[str, Any], player: str) -> dict[str, Any]:
        dice = state.get("dice") or []
        if _legal_pieces(state, player, sum(dice)):
            raise IllegalAction("you have a legal move; cannot pass")
        return {
            **state,
            "pieces": _clone_pieces(state),
            "scored": dict(state["scored"]),
            "phase": "roll",
            "dice": None,
            "turn_player": opponent_of(state["order"], player),
            "last_roll": None,
            "last_move": None,
        }

    # ---------- protocol queries ----------

    def current_player(self, state: dict[str, Any]) -> str | None:
        if self.is_terminal(state):
            return None
        return state["turn_player"]

    def winner(self, state: dict[str, Any]) -> str | None:
        return state.get("winner")

    def is_terminal(self, state: dict[str, Any]) -> bool:
        return state.get("winner") is not None

    # ---------- cursor model ----------

    def initial_cursor(self) -> dict[str, Any]:
        return {"phase": "roll", "piece_idx": 0, "legal": [], "viewer_seat": 0}

    def init_cursor_for(self, me: str, state: dict[str, Any]) -> dict[str, Any]:
        order = state.get("order", [])
        try:
            seat = order.index(me)
        except ValueError:
            seat = 0
        return {**self.initial_cursor(), "viewer_seat": seat}

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        if cursor.get("phase") != "move":
            return cursor
        legal: list[int] = list(cursor.get("legal") or [])
        if not legal:
            return cursor
        step = dc + dr  # any arrow advances; no spatial layout makes sense here
        if step == 0:
            return cursor
        try:
            current = legal.index(int(cursor.get("piece_idx", legal[0])))
        except ValueError:
            current = 0
        nxt = (current + step) % len(legal)
        return {**cursor, "piece_idx": legal[nxt]}

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        if cursor.get("phase") == "roll":
            return {"type": "roll"}
        legal: list[int] = list(cursor.get("legal") or [])
        if not legal:
            return {"type": "pass"}
        return {"type": "move", "piece_idx": int(cursor["piece_idx"])}

    def sync_cursor(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        phase = state.get("phase", "roll")
        if phase == "roll" or self.is_terminal(state):
            return {**cursor, "phase": "roll", "piece_idx": 0, "legal": []}
        turn = state.get("turn_player")
        choices = (
            _cursor_choices(state, turn, sum(state.get("dice") or [])) if turn else []
        )
        piece_idx = choices[0] if choices else 0
        prev_idx = int(cursor.get("piece_idx", piece_idx))
        if prev_idx in choices:
            piece_idx = prev_idx
        return {**cursor, "phase": "move", "piece_idx": piece_idx, "legal": choices}

    # ---------- animation ----------

    def animation_for(
        self, prev_state: dict[str, Any], new_state: dict[str, Any]
    ) -> Any | None:
        prev_roll = prev_state.get("last_roll")
        new_roll = new_state.get("last_roll")
        if new_roll is not None and new_roll != prev_roll:
            spins = [_roll_dice() for _ in range(5)]
            return _DiceAnimation(final=list(new_roll["dice"]), spins=spins)

        prev_move = prev_state.get("last_move")
        new_move = new_state.get("last_move")
        if new_move is not None and new_move != prev_move:
            player = new_move["player"]
            seat = _seat_of(new_state, player)
            from_pos = int(new_move["from"])
            to_pos = int(new_move["to"])
            track = _track_for(seat)
            # Build per-frame xy: each step from from_pos+1 .. to_pos.
            path_xy: list[tuple[int, int] | None] = []
            for pos in range(from_pos + 1, to_pos + 1):
                path_xy.append(track[pos] if 0 < pos < HOME else None)
            if not path_xy:
                return None
            captured_xy: tuple[int, int] | None = None
            captured_glyph: str | None = None
            if new_move.get("captured_idx") is not None:
                captured_xy = _xy(seat, to_pos)  # both tracks share this cell
                captured_glyph = GLYPH[1 - seat]
            return _MoveAnimation(
                player=player,
                seat=seat,
                piece_idx=int(new_move["piece_idx"]),
                glyph=GLYPH[seat],
                path_xy=path_xy,
                capture_xy=captured_xy,
                capture_glyph=captured_glyph,
            )
        return None

    # ---------- rendering ----------

    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]:
        ui = ui or {}
        cursor = ui.get("cursor") or {}
        active = bool(ui.get("active", True))
        theme = ui.get("theme")
        anim = ui.get("animation") or None
        me = ui.get("player")

        order = state["order"]
        p1, p2 = order
        seat_of_me = order.index(me) if me in order else 0
        # Board convention: the viewer's own lane sits at the bottom of the
        # display, their opponent's at the top. Seat-0's lane is logical row 0,
        # seat-1's is logical row 2, so flipping hinges on `viewer_seat`.
        viewer_seat = int(cursor.get("viewer_seat", seat_of_me))
        flip = viewer_seat == 0
        display_rows = [2, 1, 0] if flip else [0, 1, 2]
        top_player, bottom_player = (p2, p1) if flip else (p1, p2)
        top_seat, bottom_seat = (1, 0) if flip else (0, 1)

        grid_sty = style(theme, "primary")
        muted = style(theme, "muted")
        head_sty = header_palette(theme)
        rosette_sty = style(theme, "warning", bold=True)
        rosette_safe_bg = bg_style(theme, "warning")
        cursor_active, cursor_inactive = cursor_palette(theme)
        cursor_sty = cursor_active if active else cursor_inactive
        sty_by_seat = {
            0: style(theme, "success", bold=True),
            1: style(theme, "error", bold=True),
        }

        moving = anim if anim and anim.get("kind") == "move" else None
        dice_overlay = anim if anim and anim.get("kind") == "dice" else None

        # ----- compute board occupancy for rendering -----
        # cell_glyph[(r,c)] = (glyph, style) for the static piece-on-cell render.
        # `moving` overrides: hides the source piece, draws the in-flight glyph,
        # and toggles the captured piece during the flash window.
        cell: dict[tuple[int, int], tuple[str, Style]] = {}
        for seat, pl in enumerate(order):
            for idx, pos in enumerate(state["pieces"][pl]):
                if 1 <= pos <= TRACK_LEN:
                    rc = _xy(seat, pos)
                    if rc is not None:
                        cell[rc] = (GLYPH[seat], sty_by_seat[seat])

        if moving is not None:
            mover = moving["player"]
            mseat = order.index(mover)
            mpos = state["pieces"][mover][int(moving["piece_idx"])]
            if 1 <= mpos <= TRACK_LEN:
                src = _xy(mseat, mpos)
                if src in cell:
                    del cell[src]
            xy = moving.get("xy")
            if xy is not None:
                cell[(int(xy[0]), int(xy[1]))] = (moving["glyph"], sty_by_seat[mseat])
            cap_xy = moving.get("capture_xy")
            cap_glyph = moving.get("capture_glyph")
            if cap_xy is not None and not moving.get("capture_visible", True):
                rc = (int(cap_xy[0]), int(cap_xy[1]))
                if cap_glyph is not None and cell.get(rc, (None, None))[0] == cap_glyph:
                    del cell[rc]

        # Cursor highlight target — only meaningful in move phase.
        cursor_xy: tuple[int, int] | None = None
        cursor_pool_seat: int | None = None  # whole pool highlighted as one choice
        if cursor.get("phase") == "move" and active and cursor.get("legal"):
            idx = int(cursor.get("piece_idx", 0))
            seat = seat_of_me
            pos = state["pieces"][me][idx] if me in state["pieces"] else POOL
            if pos == POOL:
                cursor_pool_seat = seat
            elif 1 <= pos <= TRACK_LEN:
                cursor_xy = _xy(seat, pos)

        # ----- top-of-board: opponent header + pool -----
        score_sty = style(theme, "accent", bold=True)
        active_sty = style(theme, "warning", bold=True)
        lines: list[Strip] = []
        lines.append(
            self._player_header(
                state,
                top_player,
                top_seat,
                sty_by_seat[top_seat],
                head_sty,
                score_sty,
                active_sty,
            )
        )
        lines.append(
            self._pool_strip(
                state,
                top_player,
                top_seat,
                cursor_pool_seat,
                cursor_sty,
                sty_by_seat[top_seat],
                muted,
                head_sty,
            )
        )

        # ----- the 3-row board (rows reordered when flipped) -----
        # Separators depend only on which neighbors have gap-cols: SEP_R0_R1
        # always sits adjacent to a gap-row above the middle, SEP_R1_R2 below.
        # Borders are symmetric so they don't change with flip.
        lines.append(Strip([Segment(TOP_BORDER, grid_sty)]))
        lines.append(
            self._board_row(
                display_rows[0],
                cell,
                cursor_xy,
                cursor_sty,
                grid_sty,
                rosette_sty,
                rosette_safe_bg,
            )
        )
        lines.append(Strip([Segment(SEP_R0_R1, grid_sty)]))
        lines.append(
            self._board_row(
                display_rows[1],
                cell,
                cursor_xy,
                cursor_sty,
                grid_sty,
                rosette_sty,
                rosette_safe_bg,
            )
        )
        lines.append(Strip([Segment(SEP_R1_R2, grid_sty)]))
        lines.append(
            self._board_row(
                display_rows[2],
                cell,
                cursor_xy,
                cursor_sty,
                grid_sty,
                rosette_sty,
                rosette_safe_bg,
            )
        )
        lines.append(Strip([Segment(BOT_BORDER, grid_sty)]))

        # ----- bottom-of-board: viewer's own header + pool -----
        lines.append(
            self._pool_strip(
                state,
                bottom_player,
                bottom_seat,
                cursor_pool_seat,
                cursor_sty,
                sty_by_seat[bottom_seat],
                muted,
                head_sty,
            )
        )
        lines.append(
            self._player_header(
                state,
                bottom_player,
                bottom_seat,
                sty_by_seat[bottom_seat],
                head_sty,
                score_sty,
                active_sty,
            )
        )

        # ----- dice strip -----
        lines.append(Strip([Segment("")]))
        lines.append(self._dice_strip(state, dice_overlay, theme, head_sty))

        # ----- status -----
        lines.append(status_strip(self._status(state, cursor, me, dice_overlay)))
        return lines

    # ---------- render helpers ----------

    def _player_header(
        self,
        state: dict[str, Any],
        player: str,
        seat: int,
        piece_sty: Style,
        head_sty: Style,
        score_sty: Style,
        active_sty: Style,
    ) -> Strip:
        active = state.get("turn_player") == player and not self.is_terminal(state)
        prefix = "  ▸ " if active else "    "
        scored = int(state["scored"][player])
        marker = "(turn)" if active else ""
        return Strip(
            [
                Segment(prefix, active_sty if active else head_sty),
                Segment(GLYPH[seat], piece_sty),
                Segment(f"  {player}  ", head_sty),
                Segment(f"home {scored}/{NUM_PIECES}  ", score_sty),
                Segment(marker, head_sty),
            ]
        )

    def _pool_strip(
        self,
        state: dict[str, Any],
        player: str,
        seat: int,
        cursor_pool_seat: int | None,
        cursor_sty: Style,
        piece_sty: Style,
        muted: Style,
        head_sty: Style,
    ) -> Strip:
        pieces = state["pieces"][player]
        pool_selected = cursor_pool_seat == seat
        segs: list[Segment] = [Segment("    pool  ", head_sty)]
        for idx in range(NUM_PIECES):
            pos = pieces[idx]
            if pos == POOL:
                glyph = GLYPH[seat]
                if pool_selected:
                    # Whole pool is one cursor choice — bracket every filled
                    # slot so the user reads the row as a single selection.
                    segs.extend(
                        [
                            Segment("[", cursor_sty),
                            Segment(glyph, cursor_sty),
                            Segment("]", cursor_sty),
                        ]
                    )
                else:
                    segs.extend([Segment(" "), Segment(glyph, piece_sty), Segment(" ")])
            else:
                segs.extend([Segment(" "), Segment("·", muted), Segment(" ")])
        return Strip(segs)

    def _board_row(
        self,
        row: int,
        cell: dict[tuple[int, int], tuple[str, Style]],
        cursor_xy: tuple[int, int] | None,
        cursor_sty: Style,
        grid_sty: Style,
        rosette_sty: Style,
        rosette_safe_bg: Style,
    ) -> Strip:
        present = ROW_PRESENT[row]

        def sep(left: int, right: int | None) -> Segment:
            # Vertical wall when either neighboring cell exists in this row.
            left_p = 0 <= left <= 7 and left in present
            right_p = right is not None and 0 <= right <= 7 and right in present
            return Segment("│" if (left_p or right_p) else " ", grid_sty)

        segs: list[Segment] = [sep(-1, 0)]
        for c in range(8):
            if c not in present:
                segs.append(Segment("   "))
            else:
                piece = cell.get((row, c))
                is_rosette = self._is_rosette_cell(row, c)
                is_cursor = cursor_xy == (row, c)
                if is_cursor:
                    glyph = piece[0] if piece else " "
                    segs.extend(
                        [
                            Segment("[", cursor_sty),
                            Segment(glyph, cursor_sty),
                            Segment("]", cursor_sty),
                        ]
                    )
                elif piece is not None:
                    if is_rosette:
                        segs.extend(
                            [
                                Segment(" ", rosette_safe_bg),
                                Segment(piece[0], piece[1] + rosette_safe_bg),
                                Segment(" ", rosette_safe_bg),
                            ]
                        )
                    else:
                        segs.extend(
                            [Segment(" "), Segment(piece[0], piece[1]), Segment(" ")]
                        )
                elif is_rosette:
                    segs.extend(
                        [
                            Segment(" "),
                            Segment(ROSETTE_GLYPH, rosette_sty),
                            Segment(" "),
                        ]
                    )
                else:
                    segs.append(Segment("   "))
            segs.append(sep(c, c + 1 if c < 7 else None))
        return Strip(segs)

    def _is_rosette_cell(self, row: int, col: int) -> bool:
        return (row, col) in _ROSETTE_CELLS

    def _dice_strip(
        self,
        state: dict[str, Any],
        dice_overlay: dict[str, Any] | None,
        theme: dict[str, Any] | None,
        head_sty: Style,
    ) -> Strip:
        if dice_overlay is not None:
            values = list(dice_overlay.get("values") or [])
            total = dice_overlay.get("sum")
            settled = dice_overlay.get("settled", False)
        else:
            values = list(state.get("dice") or [])
            total = sum(values) if values else None
            settled = True
        on_sty = style(theme, "warning", bold=True)
        off_sty = style(theme, "muted")
        segs: list[Segment] = [Segment("    dice  ", head_sty)]
        if not values:
            segs.append(Segment("— — — —", off_sty))
        else:
            for v in values:
                glyph = "▲" if v == 1 else "△"
                segs.append(Segment(f" {glyph} ", on_sty if v == 1 else off_sty))
        if total is not None and (settled or values):
            segs.append(Segment(f"   sum: {total}", head_sty))
        return Strip(segs)

    def _status(
        self,
        state: dict[str, Any],
        cursor: dict[str, Any],
        me: str | None,
        dice_overlay: dict[str, Any] | None,
    ) -> str:
        winner = state.get("winner")
        if winner:
            return f"  {winner} wins!"
        turn = state["turn_player"]
        phase = state.get("phase", "roll")
        if phase == "roll":
            if turn == me:
                return "  enter: roll dice"
            return f"  waiting for {turn} to roll…"
        # move phase
        if turn == me:
            legal = list(cursor.get("legal") or [])
            if not legal:
                ds = sum(state.get("dice") or [])
                return f"  rolled {ds} — no legal moves, enter: pass"
            return "  ←/→: pick piece, enter: move"
        ds = sum(state.get("dice") or [])
        return f"  waiting for {turn} to move ({ds})…"

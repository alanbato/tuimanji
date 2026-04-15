"""Chess — full FIDE rules minus the draw-by-repetition / 50-move / insufficient-material rules.

State, actions, and legal-move generation are pure functions so the game is
unit-testable without Textual. The cursor machine has three modes:

    select   — arrows move hover square, space picks piece under cursor
    target   — arrows move destination, space cancels, enter commits
    promote  — arrows pick Q/R/B/N, space backs out, enter commits move

The select→target and target→promote transitions don't need the state dict
(stage_cursor runs blind), but target→promote needs to know whether the move
is a pawn push to the last rank, so that transition uses `prepare_action`
which receives state. MatchScreen calls `prepare_action` via getattr; games
that don't implement it work unchanged.
"""

from typing import Any

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import style
from ._common import (
    cell_segments,
    copy_grid,
    cursor_bracket,
    cursor_palette,
    empty_grid,
    header_palette,
    in_bounds,
    opponent_of,
    status_strip,
    wrap_cursor,
)

SIZE = 8
EMPTY_CELL = ""

PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = "P", "N", "B", "R", "Q", "K"
WHITE, BLACK = "w", "b"
PROMO_PIECES = [QUEEN, ROOK, BISHOP, KNIGHT]

GLYPHS: dict[str, str] = {
    "wK": "♚",
    "wQ": "♛",
    "wR": "♜",
    "wB": "♝",
    "wN": "♞",
    "wP": "♟",
    "bK": "♚",
    "bQ": "♛",
    "bR": "♜",
    "bB": "♝",
    "bN": "♞",
    "bP": "♟",
}

FILE_LABELS = "abcdefgh"

KNIGHT_DELTAS: list[tuple[int, int]] = [
    (-2, -1),
    (-2, 1),
    (-1, -2),
    (-1, 2),
    (1, -2),
    (1, 2),
    (2, -1),
    (2, 1),
]
BISHOP_DIRS: list[tuple[int, int]] = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
ROOK_DIRS: list[tuple[int, int]] = [(-1, 0), (1, 0), (0, -1), (0, 1)]
KING_DELTAS: list[tuple[int, int]] = BISHOP_DIRS + ROOK_DIRS


def piece_color(p: str) -> str:
    return p[0] if p else ""


def piece_kind(p: str) -> str:
    return p[1] if p else ""


def _initial_board() -> list[list[str]]:
    b = empty_grid(SIZE, SIZE, fill=EMPTY_CELL)
    back = [ROOK, KNIGHT, BISHOP, QUEEN, KING, BISHOP, KNIGHT, ROOK]
    for c in range(SIZE):
        b[0][c] = BLACK + back[c]
        b[1][c] = BLACK + PAWN
        b[6][c] = WHITE + PAWN
        b[7][c] = WHITE + back[c]
    return b


def _pseudo_moves(
    board: list[list[str]],
    r: int,
    c: int,
    castling: dict[str, dict[str, bool]],
    en_passant: list[int] | None,
) -> list[tuple[int, int]]:
    """Moves the piece at (r,c) could make ignoring own-king safety."""
    piece = board[r][c]
    if not piece:
        return []
    color = piece_color(piece)
    kind = piece_kind(piece)
    moves: list[tuple[int, int]] = []

    if kind == PAWN:
        direction = -1 if color == WHITE else 1
        start_row = 6 if color == WHITE else 1
        fr_one = r + direction
        if in_bounds(fr_one, c, SIZE, SIZE) and not board[fr_one][c]:
            moves.append((fr_one, c))
            fr_two = r + 2 * direction
            if (
                r == start_row
                and in_bounds(fr_two, c, SIZE, SIZE)
                and not board[fr_two][c]
            ):
                moves.append((fr_two, c))
        for dc in (-1, 1):
            cc = c + dc
            if not in_bounds(fr_one, cc, SIZE, SIZE):
                continue
            target = board[fr_one][cc]
            if target and piece_color(target) != color:
                moves.append((fr_one, cc))
            elif not target and en_passant is not None and [fr_one, cc] == en_passant:
                moves.append((fr_one, cc))

    elif kind == KNIGHT:
        for dr, dc in KNIGHT_DELTAS:
            rr, cc = r + dr, c + dc
            if not in_bounds(rr, cc, SIZE, SIZE):
                continue
            target = board[rr][cc]
            if not target or piece_color(target) != color:
                moves.append((rr, cc))

    elif kind in (BISHOP, ROOK, QUEEN):
        dirs: list[tuple[int, int]] = []
        if kind in (BISHOP, QUEEN):
            dirs.extend(BISHOP_DIRS)
        if kind in (ROOK, QUEEN):
            dirs.extend(ROOK_DIRS)
        for dr, dc in dirs:
            rr, cc = r + dr, c + dc
            while in_bounds(rr, cc, SIZE, SIZE):
                target = board[rr][cc]
                if not target:
                    moves.append((rr, cc))
                else:
                    if piece_color(target) != color:
                        moves.append((rr, cc))
                    break
                rr += dr
                cc += dc

    elif kind == KING:
        for dr, dc in KING_DELTAS:
            rr, cc = r + dr, c + dc
            if not in_bounds(rr, cc, SIZE, SIZE):
                continue
            target = board[rr][cc]
            if not target or piece_color(target) != color:
                moves.append((rr, cc))
        rights = castling.get(color, {})
        home_row = 7 if color == WHITE else 0
        if r == home_row and c == 4:
            # Kingside: squares f/g empty, rook on h.
            if (
                rights.get("K")
                and not board[home_row][5]
                and not board[home_row][6]
                and board[home_row][7] == color + ROOK
            ):
                moves.append((home_row, 6))
            # Queenside: squares b/c/d empty, rook on a.
            if (
                rights.get("Q")
                and not board[home_row][1]
                and not board[home_row][2]
                and not board[home_row][3]
                and board[home_row][0] == color + ROOK
            ):
                moves.append((home_row, 2))

    return moves


def _is_attacked(board: list[list[str]], r: int, c: int, by_color: str) -> bool:
    """True if any piece of `by_color` attacks square (r,c)."""
    for dr, dc in KNIGHT_DELTAS:
        rr, cc = r + dr, c + dc
        if in_bounds(rr, cc, SIZE, SIZE) and board[rr][cc] == by_color + KNIGHT:
            return True
    # Pawns: a white pawn on (r+1, c±1) attacks (r, c); symmetric for black.
    pawn_from_dr = 1 if by_color == WHITE else -1
    for dc in (-1, 1):
        rr, cc = r + pawn_from_dr, c + dc
        if in_bounds(rr, cc, SIZE, SIZE) and board[rr][cc] == by_color + PAWN:
            return True
    for dr, dc in KING_DELTAS:
        rr, cc = r + dr, c + dc
        if in_bounds(rr, cc, SIZE, SIZE) and board[rr][cc] == by_color + KING:
            return True
    for dr, dc in BISHOP_DIRS:
        rr, cc = r + dr, c + dc
        while in_bounds(rr, cc, SIZE, SIZE):
            p = board[rr][cc]
            if p:
                if piece_color(p) == by_color and piece_kind(p) in (BISHOP, QUEEN):
                    return True
                break
            rr += dr
            cc += dc
    for dr, dc in ROOK_DIRS:
        rr, cc = r + dr, c + dc
        while in_bounds(rr, cc, SIZE, SIZE):
            p = board[rr][cc]
            if p:
                if piece_color(p) == by_color and piece_kind(p) in (ROOK, QUEEN):
                    return True
                break
            rr += dr
            cc += dc
    return False


def _find_king(board: list[list[str]], color: str) -> tuple[int, int] | None:
    target = color + KING
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] == target:
                return (r, c)
    return None


def _in_check(board: list[list[str]], color: str) -> bool:
    king = _find_king(board, color)
    if king is None:
        return False
    enemy = BLACK if color == WHITE else WHITE
    return _is_attacked(board, king[0], king[1], enemy)


def _apply_move_on_board(
    board: list[list[str]],
    from_rc: tuple[int, int],
    to_rc: tuple[int, int],
    castling: dict[str, dict[str, bool]],
    en_passant: list[int] | None,
    promote: str | None,
) -> tuple[
    list[list[str]],
    dict[str, dict[str, bool]],
    list[int] | None,
    str | None,
    str | None,
    str | None,
]:
    """Execute a single move on a copy of the board.

    Returns (new_board, new_castling, new_en_passant, special, captured, promoted).
    `special` is one of None / "castle_K" / "castle_Q" / "enpassant".
    """
    fr, fc = from_rc
    tr, tc = to_rc
    b = copy_grid(board)
    piece = b[fr][fc]
    color = piece_color(piece)
    kind = piece_kind(piece)
    captured: str | None = b[tr][tc] or None
    special: str | None = None
    promoted: str | None = None

    if (
        kind == PAWN
        and en_passant is not None
        and [tr, tc] == en_passant
        and not b[tr][tc]
        and fc != tc
    ):
        cap_row = tr + (1 if color == WHITE else -1)
        captured = b[cap_row][tc] or None
        b[cap_row][tc] = EMPTY_CELL
        special = "enpassant"

    b[tr][tc] = piece
    b[fr][fc] = EMPTY_CELL

    if kind == PAWN and (tr == 0 or tr == SIZE - 1):
        promo_kind = promote or QUEEN
        b[tr][tc] = color + promo_kind
        promoted = b[tr][tc]

    if kind == KING and abs(tc - fc) == 2:
        home_row = fr
        if tc == 6:
            b[home_row][5] = b[home_row][7]
            b[home_row][7] = EMPTY_CELL
            special = "castle_K"
        else:
            b[home_row][3] = b[home_row][0]
            b[home_row][0] = EMPTY_CELL
            special = "castle_Q"

    new_castling: dict[str, dict[str, bool]] = {
        WHITE: dict(castling.get(WHITE, {"K": True, "Q": True})),
        BLACK: dict(castling.get(BLACK, {"K": True, "Q": True})),
    }
    if kind == KING and color in new_castling:
        new_castling[color] = {"K": False, "Q": False}
    if kind == ROOK and color in new_castling:
        home_row = 7 if color == WHITE else 0
        if fr == home_row and fc == 0:
            new_castling[color]["Q"] = False
        elif fr == home_row and fc == 7:
            new_castling[color]["K"] = False
    if captured and piece_kind(captured) == ROOK:
        cap_color = piece_color(captured)
        if cap_color in new_castling:
            cap_home = 7 if cap_color == WHITE else 0
            if tr == cap_home and tc == 0:
                new_castling[cap_color]["Q"] = False
            elif tr == cap_home and tc == 7:
                new_castling[cap_color]["K"] = False

    new_ep: list[int] | None = None
    if kind == PAWN and abs(tr - fr) == 2:
        new_ep = [(tr + fr) // 2, tc]

    return b, new_castling, new_ep, special, captured, promoted


def _legal_destinations(
    board: list[list[str]],
    r: int,
    c: int,
    castling: dict[str, dict[str, bool]],
    en_passant: list[int] | None,
) -> list[tuple[int, int]]:
    piece = board[r][c]
    if not piece:
        return []
    color = piece_color(piece)
    enemy = BLACK if color == WHITE else WHITE
    out: list[tuple[int, int]] = []
    for tr, tc in _pseudo_moves(board, r, c, castling, en_passant):
        if piece_kind(piece) == KING and abs(tc - c) == 2:
            if _in_check(board, color):
                continue
            step = 1 if tc > c else -1
            blocked = False
            for nc in (c + step, c + 2 * step):
                if _is_attacked(board, r, nc, enemy):
                    blocked = True
                    break
            if blocked:
                continue
        new_b, _, _, _, _, _ = _apply_move_on_board(
            board, (r, c), (tr, tc), castling, en_passant, promote=None
        )
        if not _in_check(new_b, color):
            out.append((tr, tc))
    return out


def _any_legal_move(
    board: list[list[str]],
    color: str,
    castling: dict[str, dict[str, bool]],
    en_passant: list[int] | None,
) -> bool:
    for r in range(SIZE):
        for c in range(SIZE):
            p = board[r][c]
            if p and piece_color(p) == color:
                if _legal_destinations(board, r, c, castling, en_passant):
                    return True
    return False


class Chess:
    id = "chess"
    name = "Chess"
    min_players = 2
    max_players = 2

    # ---------- lifecycle ----------

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 2:
            raise ValueError("chess requires exactly 2 players")
        p1, p2 = players
        return {
            "board": _initial_board(),
            "marks": {p1: WHITE, p2: BLACK},
            "order": [p1, p2],
            "turn_player": p1,
            "winner": None,
            "castling": {
                WHITE: {"K": True, "Q": True},
                BLACK: {"K": True, "Q": True},
            },
            "en_passant": None,
            "halfmove": 0,
            "fullmove": 1,
            "last_move": None,
            "in_check": None,
            "result": None,
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if self.is_terminal(state):
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")
        if action.get("type") != "move":
            raise IllegalAction(f"expected move, got {action.get('type')}")
        try:
            fr = int(action["from"][0])
            fc = int(action["from"][1])
            tr = int(action["to"][0])
            tc = int(action["to"][1])
        except (KeyError, TypeError, ValueError, IndexError) as e:
            raise IllegalAction(f"bad move action: {action}") from e
        if not (in_bounds(fr, fc, SIZE, SIZE) and in_bounds(tr, tc, SIZE, SIZE)):
            raise IllegalAction(f"out of bounds: ({fr},{fc})->({tr},{tc})")

        board = state["board"]
        piece = board[fr][fc]
        if not piece:
            raise IllegalAction(f"no piece at ({fr},{fc})")
        color = state["marks"][player]
        if piece_color(piece) != color:
            raise IllegalAction(f"{piece} is not yours")

        castling = state["castling"]
        en_passant = state.get("en_passant")
        legal = _legal_destinations(board, fr, fc, castling, en_passant)
        if (tr, tc) not in legal:
            raise IllegalAction(f"illegal move for {piece}: ({fr},{fc})->({tr},{tc})")

        promote_piece: str | None = None
        if piece_kind(piece) == PAWN and (tr == 0 or tr == SIZE - 1):
            promote_in = action.get("promote")
            if promote_in is None:
                raise IllegalAction("promotion piece required")
            if promote_in not in PROMO_PIECES:
                raise IllegalAction(f"invalid promotion piece: {promote_in}")
            promote_piece = str(promote_in)

        (
            new_board,
            new_castling,
            new_ep,
            special,
            captured,
            promoted,
        ) = _apply_move_on_board(
            board,
            (fr, fc),
            (tr, tc),
            castling,
            en_passant,
            promote=promote_piece,
        )

        opp_color = BLACK if color == WHITE else WHITE
        opp_player = opponent_of(state["order"], player)
        opp_in_check = _in_check(new_board, opp_color)
        opp_has_moves = _any_legal_move(new_board, opp_color, new_castling, new_ep)

        result: str | None = None
        winner: str | None = None
        if not opp_has_moves:
            if opp_in_check:
                result = "checkmate"
                winner = player
            else:
                result = "stalemate"
                winner = "draw"

        reset_halfmove = piece_kind(piece) == PAWN or captured is not None
        halfmove = 0 if reset_halfmove else int(state.get("halfmove", 0)) + 1
        fullmove = int(state.get("fullmove", 1)) + (1 if color == BLACK else 0)

        return {
            **state,
            "board": new_board,
            "castling": new_castling,
            "en_passant": new_ep,
            "halfmove": halfmove,
            "fullmove": fullmove,
            "turn_player": opp_player,
            "last_move": {
                "from": [fr, fc],
                "to": [tr, tc],
                "piece": piece,
                "captured": captured,
                "promoted": promoted,
                "special": special,
            },
            "in_check": opp_color if opp_in_check else None,
            "result": result,
            "winner": winner,
        }

    # ---------- protocol queries ----------

    def current_player(self, state: dict[str, Any]) -> str | None:
        if self.is_terminal(state):
            return None
        return state["turn_player"]

    def winner(self, state: dict[str, Any]) -> str | None:
        w = state.get("winner")
        if w is None or w == "draw":
            return None
        return w

    def is_terminal(self, state: dict[str, Any]) -> bool:
        return state.get("winner") is not None

    # ---------- cursor ----------

    def initial_cursor(self) -> dict[str, Any]:
        return {
            "mode": "select",
            "row": 6,
            "col": 4,
            "from": None,
            "promote_idx": 0,
            "pending_to": None,
            "viewer_seat": 0,
        }

    def init_cursor_for(self, me: str, state: dict[str, Any]) -> dict[str, Any]:
        order = state.get("order", [])
        try:
            seat = order.index(me)
        except ValueError:
            seat = 0
        start_row = 1 if seat == 1 else 6
        return {
            **self.initial_cursor(),
            "row": start_row,
            "col": 4,
            "viewer_seat": seat,
        }

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        if cursor["mode"] == "promote":
            if dc == 0:
                return cursor
            return {
                **cursor,
                "promote_idx": (cursor["promote_idx"] + dc) % len(PROMO_PIECES),
            }
        if cursor.get("viewer_seat", 0) == 1:
            dr, dc = -dr, -dc
        return wrap_cursor(cursor, dr, dc, SIZE, SIZE)

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        mode = cursor["mode"]
        if mode == "select":
            raise IllegalAction("no piece selected")
        if mode == "target":
            frm = cursor.get("from")
            if frm is None:
                raise IllegalAction("no piece selected")
            return {
                "type": "move",
                "from": [int(frm[0]), int(frm[1])],
                "to": [cursor["row"], cursor["col"]],
            }
        if mode == "promote":
            frm = cursor.get("from")
            pend = cursor.get("pending_to")
            if frm is None or pend is None:
                raise IllegalAction("no pending promotion")
            return {
                "type": "move",
                "from": [int(frm[0]), int(frm[1])],
                "to": [int(pend[0]), int(pend[1])],
                "promote": PROMO_PIECES[cursor["promote_idx"]],
            }
        raise IllegalAction(f"unknown cursor mode: {mode}")

    # Optional hooks — MatchScreen probes these via getattr.

    def stage_cursor(self, cursor: dict[str, Any]) -> dict[str, Any]:
        mode = cursor["mode"]
        if mode == "select":
            return {
                **cursor,
                "mode": "target",
                "from": [cursor["row"], cursor["col"]],
            }
        if mode == "target":
            frm = cursor.get("from")
            row, col = (
                (frm[0], frm[1]) if frm is not None else (cursor["row"], cursor["col"])
            )
            return {
                **cursor,
                "mode": "select",
                "row": row,
                "col": col,
                "from": None,
            }
        if mode == "promote":
            return {
                **cursor,
                "mode": "target",
                "pending_to": None,
                "promote_idx": 0,
            }
        return cursor

    def prepare_action(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Intercept Enter in target mode to transition into promote mode.

        Returns a new cursor when a transition should happen (MatchScreen will
        update and skip submitting), or None to let cursor_action submit.
        """
        if cursor["mode"] != "target":
            return None
        frm = cursor.get("from")
        if frm is None:
            return None
        fr, fc = int(frm[0]), int(frm[1])
        board = state.get("board")
        if not board:
            return None
        if not in_bounds(fr, fc, SIZE, SIZE):
            return None
        piece = board[fr][fc]
        if piece_kind(piece) != PAWN:
            return None
        tr = cursor["row"]
        if tr != 0 and tr != SIZE - 1:
            return None
        return {
            **cursor,
            "mode": "promote",
            "pending_to": [tr, cursor["col"]],
            "promote_idx": 0,
        }

    def sync_cursor(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        if cursor["mode"] == "select":
            return cursor
        return {
            **cursor,
            "mode": "select",
            "from": None,
            "promote_idx": 0,
            "pending_to": None,
        }

    # ---------- animation ----------

    def animation_for(
        self, prev_state: dict[str, Any], new_state: dict[str, Any]
    ) -> None:
        return None

    # ---------- render ----------

    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]:
        ui = ui or {}
        cursor = ui.get("cursor") or {}
        active = ui.get("active", True)
        theme = ui.get("theme")

        order = state.get("order", [])
        marks = state.get("marks", {})
        flipped = int(cursor.get("viewer_seat", 0)) == 1

        def to_board(dr: int, dc: int) -> tuple[int, int]:
            return (SIZE - 1 - dr, SIZE - 1 - dc) if flipped else (dr, dc)

        board = state["board"]
        grid_style = style(theme, "primary")
        empty_style = style(theme, "muted")
        white_style = style(theme, "foreground", bold=True)
        black_style = style(theme, "accent", bold=True)
        hint_style = style(theme, "success", bold=True)
        underline_style = Style(underline=True)
        cursor_active, cursor_inactive = cursor_palette(theme)
        header_style = header_palette(theme)
        check_style = style(theme, "error", bold=True)

        def piece_style(p: str) -> Style:
            return white_style if piece_color(p) == WHITE else black_style

        mode = cursor.get("mode", "select")
        cur_r = int(cursor.get("row", 0))
        cur_c = int(cursor.get("col", 0))
        frm = cursor.get("from")
        from_rc: tuple[int, int] | None = None
        if frm is not None:
            from_rc = (int(frm[0]), int(frm[1]))

        legal_set: set[tuple[int, int]] = set()
        if from_rc is not None and mode in ("target", "promote"):
            legal_set = set(
                _legal_destinations(
                    board,
                    from_rc[0],
                    from_rc[1],
                    state["castling"],
                    state.get("en_passant"),
                )
            )

        last_move = state.get("last_move")
        last_from: tuple[int, int] | None = None
        last_to: tuple[int, int] | None = None
        if last_move is not None:
            lf = last_move.get("from")
            lt = last_move.get("to")
            if lf is not None:
                last_from = (int(lf[0]), int(lf[1]))
            if lt is not None:
                last_to = (int(lt[0]), int(lt[1]))

        check_king: tuple[int, int] | None = None
        check_color = state.get("in_check")
        if check_color:
            check_king = _find_king(board, str(check_color))

        # ---- strips ----

        def file_label_strip() -> Strip:
            segs: list[Segment] = [Segment("    ")]
            for dc in range(SIZE):
                _, bc = to_board(0, dc)
                segs.append(Segment(f" {FILE_LABELS[bc]}  ", header_style))
            return Strip(segs)

        def grid_line(left: str, mid: str, right: str, fill: str) -> Strip:
            body = left + (fill + mid) * (SIZE - 1) + fill + right
            return Strip([Segment("   ", header_style), Segment(body, grid_style)])

        def cell_segs(r: int, c: int) -> list[Segment]:
            piece = board[r][c]
            glyph = GLYPHS.get(piece, "·") if piece else "·"
            is_cursor = (r, c) == (cur_r, cur_c) and mode in ("select", "target")
            is_from = from_rc == (r, c)
            is_last = (r, c) == last_from or (r, c) == last_to
            is_hint = (r, c) in legal_set
            is_check_king = check_king == (r, c)

            if is_cursor:
                return cursor_bracket(
                    glyph, cursor_active if active else cursor_inactive
                )
            if is_from:
                return [
                    Segment("(", hint_style),
                    Segment(glyph, piece_style(piece) if piece else empty_style),
                    Segment(")", hint_style),
                ]
            if piece:
                base_st = check_style if is_check_king else piece_style(piece)
                if is_last:
                    base_st = base_st + underline_style
                return cell_segments(glyph, base_st)
            if is_hint:
                return cell_segments("∘", hint_style)
            if is_last:
                return cell_segments("·", empty_style + underline_style)
            return cell_segments("·", empty_style)

        def row_strip(dr: int) -> Strip:
            br, _ = to_board(dr, 0)
            rank = str(SIZE - br)
            segs: list[Segment] = [
                Segment(f" {rank} ", header_style),
                Segment("│", grid_style),
            ]
            for dc in range(SIZE):
                _, bc = to_board(dr, dc)
                segs.extend(cell_segs(br, bc))
                segs.append(Segment("│", grid_style))
            return Strip(segs)

        def header_line() -> Strip:
            parts: list[Segment] = [Segment("  ", header_style)]
            for p in order:
                tag = marks.get(p, "?")
                label = f"{p}({tag})  "
                parts.append(Segment(label, header_style))
            return Strip(parts)

        lines: list[Strip] = [
            header_line(),
            file_label_strip(),
            grid_line("┌", "┬", "┐", "───"),
        ]
        for dr in range(SIZE):
            lines.append(row_strip(dr))
            if dr < SIZE - 1:
                lines.append(grid_line("├", "┼", "┤", "───"))
        lines.append(grid_line("└", "┴", "┘", "───"))
        lines.append(file_label_strip())

        if mode == "promote":
            picker_color = marks.get(state.get("turn_player"), WHITE)
            picker_style = white_style if picker_color == WHITE else black_style
            picker_segs: list[Segment] = [Segment("    promote: ", header_style)]
            for i, kind in enumerate(PROMO_PIECES):
                glyph = GLYPHS[picker_color + kind]
                if i == int(cursor.get("promote_idx", 0)):
                    picker_segs.extend(cursor_bracket(glyph, cursor_active))
                else:
                    picker_segs.extend(cell_segments(glyph, picker_style))
            lines.append(Strip(picker_segs))

        lines.append(Strip([Segment("")]))
        lines.append(status_strip(self._status(state, cursor, ui.get("player"))))
        return lines

    def _status(
        self,
        state: dict[str, Any],
        cursor: dict[str, Any],
        me: str | None,
    ) -> str:
        result = state.get("result")
        winner = state.get("winner")
        if result == "checkmate" and winner:
            return f"  checkmate — {winner} wins"
        if result == "stalemate":
            return "  stalemate — draw"
        turn = state.get("turn_player")
        color = state.get("marks", {}).get(turn, "?")
        base = f"  turn: {turn} ({color})"
        if state.get("in_check"):
            base += "  — check!"
        if me == turn:
            mode = cursor.get("mode", "select")
            if mode == "select":
                base += "  — space: pick piece"
            elif mode == "target":
                base += "  — enter: move, space: cancel"
            elif mode == "promote":
                base += "  — ←/→ pick, enter: promote, space: back"
        return base

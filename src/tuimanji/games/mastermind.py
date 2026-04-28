"""Mastermind — codemaker hides a 4-color code, codebreaker has 10 guesses.

Best-of-three rounds. The two players alternate codemaker / codebreaker
roles each round; the first to win two rounds takes the match.

Two phases keyed off ``state["phase"]``:

- ``"set"`` — current codemaker submits ``{"code": [int, int, int, int]}``
  with each entry in ``1..6``; phase advances to ``"guess"``.
- ``"guess"`` — current codebreaker submits ``{"code": [...]}`` and the
  engine appends ``{"guess", "black", "white"}`` to ``state.current.guesses``.
  ``black`` is the count of right-color-right-position pegs;
  ``white`` is the count of right-color-wrong-position pegs (multiset
  scoring — duplicates handled correctly).

Hidden information: the active code is masked from the codebreaker via
``ui["viewer"]``. After each round ends the round record (with the
revealed code) is appended to ``state.round_history``.
"""

from typing import Any, cast

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import style
from ._common import (
    cursor_palette,
    header_palette,
    status_strip,
)

CODE_LEN = 4
NUM_COLORS = 6
MAX_GUESSES = 10
ROUNDS_TO_WIN = 2
MAX_ROUNDS = 3

# Map each peg color (1..NUM_COLORS) to a semantic theme key. Rendered
# colors track the active Textual theme rather than hardcoded literals.
COLOR_KEYS: dict[int, str] = {
    1: "error",
    2: "warning",
    3: "accent",
    4: "success",
    5: "primary",
    6: "foreground",
}
COLOR_LABEL: dict[int, str] = {
    1: "R",
    2: "O",
    3: "M",
    4: "G",
    5: "B",
    6: "W",
}


def _maker_breaker(order: list[str], round_idx: int) -> tuple[str, str]:
    """Return (codemaker, codebreaker) for the round, alternating each round."""
    return order[round_idx % 2], order[(round_idx + 1) % 2]


def _validate_code(raw: Any) -> list[int]:
    if not isinstance(raw, list) or len(raw) != CODE_LEN:
        raise IllegalAction(f"code must be {CODE_LEN} colors")
    out: list[int] = []
    for v in raw:
        try:
            iv = int(v)
        except (TypeError, ValueError) as e:
            raise IllegalAction(f"bad color: {v}") from e
        if not (1 <= iv <= NUM_COLORS):
            raise IllegalAction(f"color out of range: {iv}")
        out.append(iv)
    return out


def _score_guess(code: list[int], guess: list[int]) -> tuple[int, int]:
    """Standard Mastermind feedback: (black, white).

    ``black`` counts exact matches (right color, right position). ``white``
    counts the multiset overlap remaining after exact matches are removed —
    so a guess of ``[1,1,2,2]`` against ``[1,2,3,4]`` scores ``(1, 1)``,
    not ``(1, 2)``.
    """
    black = 0
    code_rem: list[int] = []
    guess_rem: list[int] = []
    for c, g in zip(code, guess):
        if c == g:
            black += 1
        else:
            code_rem.append(c)
            guess_rem.append(g)
    white = 0
    for g in guess_rem:
        if g in code_rem:
            code_rem.remove(g)
            white += 1
    return black, white


class Mastermind:
    id = "mastermind"
    name = "Mastermind"
    min_players = 2
    max_players = 2

    # ---------- lifecycle ----------

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        if len(players) != 2:
            raise ValueError("mastermind requires exactly 2 players")
        order = list(players)
        maker, breaker = _maker_breaker(order, 0)
        return {
            "phase": "set",
            "order": order,
            "round": 0,
            "round_wins": {order[0]: 0, order[1]: 0},
            "round_history": [],
            "current": {
                "maker": maker,
                "breaker": breaker,
                "code": None,
                "guesses": [],
            },
            "turn_player": maker,
            "winner": None,
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if state.get("winner") is not None or state.get("phase") == "finished":
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction(f"not {player}'s turn")
        phase = state["phase"]
        if phase == "set":
            return self._apply_set(state, player, action)
        if phase == "guess":
            return self._apply_guess(state, player, action)
        raise IllegalAction(f"unknown phase: {phase}")

    def _apply_set(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if state["current"]["maker"] != player:
            raise IllegalAction(f"{player} is not the codemaker")
        code = _validate_code(action.get("code"))
        return {
            **state,
            "phase": "guess",
            "current": {**state["current"], "code": code, "guesses": []},
            "turn_player": state["current"]["breaker"],
        }

    def _apply_guess(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if state["current"]["breaker"] != player:
            raise IllegalAction(f"{player} is not the codebreaker")
        code = state["current"].get("code")
        if not isinstance(code, list):
            raise IllegalAction("code not set")
        guess = _validate_code(action.get("code"))
        black, white = _score_guess(code, guess)
        guesses = list(state["current"]["guesses"]) + [
            {"guess": guess, "black": black, "white": white}
        ]
        cracked = black == CODE_LEN
        exhausted = len(guesses) >= MAX_GUESSES and not cracked

        if not cracked and not exhausted:
            return {
                **state,
                "current": {**state["current"], "guesses": guesses},
            }

        # Round complete — score it and either advance or finish.
        round_winner = (
            state["current"]["breaker"] if cracked else state["current"]["maker"]
        )
        round_record = {
            "maker": state["current"]["maker"],
            "breaker": state["current"]["breaker"],
            "code": list(code),
            "guesses": guesses,
            "winner": round_winner,
            "cracked": cracked,
        }
        new_history = list(state["round_history"]) + [round_record]
        new_wins = {
            **state["round_wins"],
            round_winner: state["round_wins"][round_winner] + 1,
        }
        finished_current = {**state["current"], "guesses": guesses}

        match_over = (
            new_wins[round_winner] >= ROUNDS_TO_WIN or len(new_history) >= MAX_ROUNDS
        )
        if match_over:
            p1, p2 = state["order"]
            if new_wins[p1] > new_wins[p2]:
                game_winner: str | None = p1
            elif new_wins[p2] > new_wins[p1]:
                game_winner = p2
            else:
                game_winner = None
            return {
                **state,
                "phase": "finished",
                "current": finished_current,
                "round_history": new_history,
                "round_wins": new_wins,
                "winner": game_winner,
            }

        next_round = state["round"] + 1
        next_maker, next_breaker = _maker_breaker(state["order"], next_round)
        return {
            **state,
            "phase": "set",
            "round": next_round,
            "round_wins": new_wins,
            "round_history": new_history,
            "current": {
                "maker": next_maker,
                "breaker": next_breaker,
                "code": None,
                "guesses": [],
            },
            "turn_player": next_maker,
        }

    # ---------- protocol queries ----------

    def current_player(self, state: dict[str, Any]) -> str | None:
        if self.is_terminal(state):
            return None
        return state["turn_player"]

    def winner(self, state: dict[str, Any]) -> str | None:
        return state.get("winner")

    def is_terminal(self, state: dict[str, Any]) -> bool:
        return state.get("phase") == "finished"

    # ---------- cursor ----------

    def initial_cursor(self) -> dict[str, Any]:
        return {"pos": 0, "code": [1] * CODE_LEN, "phase": "set"}

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        if dr != 0:
            code = list(cursor["code"])
            pos = cursor["pos"]
            # Up arrow (dr=-1) cycles forward to the next color.
            delta = -dr
            code[pos] = ((code[pos] - 1 + delta) % NUM_COLORS) + 1
            return {**cursor, "code": code}
        if dc != 0:
            return {**cursor, "pos": (cursor["pos"] + dc) % CODE_LEN}
        return cursor

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        return {"code": list(cursor["code"])}

    def sync_cursor(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        phase = state.get("phase")
        if phase != cursor.get("phase"):
            return {"pos": 0, "code": [1] * CODE_LEN, "phase": phase}
        return cursor

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
        viewer = ui.get("player")
        theme = ui.get("theme")
        order = state.get("order", [])

        cursor_active, cursor_inactive = cursor_palette(theme)
        header_style = header_palette(theme)
        muted_sty = style(theme, "muted")
        peg_full = style(theme, "foreground", bold=True)
        peg_partial = style(theme, "muted", bold=True)
        title_sty = style(theme, "primary", bold=True)
        win_sty = style(theme, "success", bold=True)

        def color_segs(c: int) -> list[Segment]:
            label = COLOR_LABEL[c]
            return [
                Segment(" "),
                Segment(label, style(theme, COLOR_KEYS[c], bold=True)),
                Segment(" "),
            ]

        def color_cursor_segs(c: int, bg: Style) -> list[Segment]:
            label = COLOR_LABEL[c]
            return [Segment("[", bg), Segment(label, bg), Segment("]", bg)]

        def empty_slot_segs(glyph: str = "·") -> list[Segment]:
            return [Segment(" "), Segment(glyph, muted_sty), Segment(" ")]

        lines: list[Strip] = []

        # Header — round, score, role
        if len(order) == 2:
            p1, p2 = order
        else:
            p1, p2 = ("?", "?")
        wins = state.get("round_wins", {})
        round_idx = int(state.get("round", 0))
        round_n = min(round_idx + 1, MAX_ROUNDS)
        head = (
            f"  Mastermind   round {round_n}/{MAX_ROUNDS}   "
            f"{p1} {wins.get(p1, 0)} — {wins.get(p2, 0)} {p2}"
        )
        lines.append(Strip([Segment(head, title_sty)]))

        cur = state.get("current", {})
        maker = cur.get("maker", "")
        breaker = cur.get("breaker", "")
        roles = f"  maker: {maker}    breaker: {breaker}"
        lines.append(Strip([Segment(roles, header_style)]))
        lines.append(Strip([Segment("")]))

        # Past rounds — short summary
        history = state.get("round_history", [])
        if history:
            lines.append(Strip([Segment("  past rounds:", header_style)]))
            for i, rec in enumerate(history):
                tag = "cracked" if rec.get("cracked") else "code held"
                line_segs: list[Segment] = [
                    Segment(
                        f"  R{i + 1}: {rec['breaker']} {tag} ({len(rec['guesses'])}) — code ",
                        muted_sty,
                    )
                ]
                for c in rec["code"]:
                    line_segs.extend(color_segs(int(c)))
                line_segs.append(Segment(f"  → {rec['winner']}", win_sty))
                lines.append(Strip(line_segs))
            lines.append(Strip([Segment("")]))

        # Secret code row — masked unless viewer is the maker, or game finished
        code = cur.get("code")
        secret_segs: list[Segment] = [Segment("  secret: ", header_style)]
        reveal = (viewer == maker) or state.get("phase") == "finished"
        if isinstance(code, list):
            for c in code:
                if reveal:
                    secret_segs.extend(color_segs(int(c)))
                else:
                    secret_segs.extend(empty_slot_segs("?"))
        else:
            for _ in range(CODE_LEN):
                secret_segs.extend(empty_slot_segs())
        lines.append(Strip(secret_segs))
        lines.append(Strip([Segment("")]))

        # Guess history (current round)
        lines.append(Strip([Segment("  guesses:", header_style)]))
        guesses = cur.get("guesses", [])
        for i in range(MAX_GUESSES):
            row_segs: list[Segment] = [Segment(f"  {i + 1:>2}. ", muted_sty)]
            if i < len(guesses):
                g = guesses[i]
                for c in g["guess"]:
                    row_segs.extend(color_segs(int(c)))
                row_segs.append(Segment("    "))
                black = int(g["black"])
                white = int(g["white"])
                empty = CODE_LEN - black - white
                if black:
                    row_segs.append(Segment("●" * black, peg_full))
                if white:
                    row_segs.append(Segment("○" * white, peg_partial))
                if empty:
                    row_segs.append(Segment("·" * empty, muted_sty))
            else:
                for _ in range(CODE_LEN):
                    row_segs.extend(empty_slot_segs())
            lines.append(Strip(row_segs))
        lines.append(Strip([Segment("")]))

        # Input draft (only when this player is the actor)
        actor = state.get("turn_player")
        is_my_turn = viewer == actor and not self.is_terminal(state)
        phase = state.get("phase", "set")
        draft_label = "  set:    " if phase == "set" else "  guess:  "
        draft_segs: list[Segment] = [Segment(draft_label, header_style)]
        draft_code_raw = cursor.get("code")
        if (
            is_my_turn
            and isinstance(draft_code_raw, list)
            and len(draft_code_raw) == CODE_LEN
        ):
            draft_code = cast(list[int], draft_code_raw)
            pos = int(cursor.get("pos", 0))
            bg = cursor_active if active else cursor_inactive
            for i, c in enumerate(draft_code):
                if i == pos:
                    draft_segs.extend(color_cursor_segs(c, bg))
                else:
                    draft_segs.extend(color_segs(c))
        else:
            for _ in range(CODE_LEN):
                draft_segs.extend([Segment(" "), Segment("—", muted_sty), Segment(" ")])
        lines.append(Strip(draft_segs))

        # Color legend (small reference)
        legend_segs: list[Segment] = [Segment("  colors: ", muted_sty)]
        for c in range(1, NUM_COLORS + 1):
            legend_segs.extend(color_segs(c))
        lines.append(Strip(legend_segs))
        lines.append(Strip([Segment("")]))

        # Status line
        if state.get("phase") == "finished":
            w = state.get("winner")
            status = f"  match winner: {w}" if w else "  match ended in a tie"
        elif is_my_turn:
            if phase == "set":
                status = "  set the secret — ←/→ position, ↑/↓ color, enter submit"
            else:
                tries_left = MAX_GUESSES - len(guesses)
                status = (
                    f"  guess the code — {tries_left} tries left "
                    "(←/→ position, ↑/↓ color, enter submit)"
                )
        else:
            if phase == "set":
                status = f"  waiting for {maker} to set the code"
            else:
                status = f"  waiting for {breaker} to guess"
        lines.append(status_strip(status))
        return lines

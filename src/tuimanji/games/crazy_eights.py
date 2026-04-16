from __future__ import annotations

import random
from typing import Any

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.strip import Strip

from ..engine import IllegalAction
from ..ui.theme import style
from ._common import (
    cursor_bracket,
    cursor_palette,
    header_palette,
    order_header,
    status_strip,
)

SUITS = ("S", "H", "D", "C")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K")
SUIT_GLYPHS: dict[str, str] = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RED_SUITS = frozenset({"H", "D"})
DEAL_COUNT = 5


def _full_deck() -> list[str]:
    return [r + s for s in SUITS for r in RANKS]


def _suit(card: str) -> str:
    return card[1]


def _rank(card: str) -> str:
    return card[0]


def _is_eight(card: str) -> bool:
    return card[0] == "8"


def _can_play(card: str, current_suit: str, top_rank: str) -> bool:
    if _is_eight(card):
        return True
    return _suit(card) == current_suit or _rank(card) == top_rank


def _card_glyph(card: str) -> str:
    return _rank(card) + SUIT_GLYPHS[_suit(card)]


def _card_style(card: str, theme: dict[str, Any] | None) -> Style:
    if _suit(card) in RED_SUITS:
        return style(theme, "error", bold=True)
    return style(theme, "foreground", bold=True)


def _next_player(order: list[str], current: str) -> str:
    return order[(order.index(current) + 1) % len(order)]


def _counts(hands: dict[str, list[str]]) -> dict[str, int]:
    return {p: len(h) for p, h in hands.items()}


def _anyone_can_play(state: dict[str, Any]) -> bool:
    top = state["discard"][-1]
    suit = state["current_suit"]
    rank = _rank(top)
    return any(
        any(_can_play(c, suit, rank) for c in hand) for hand in state["hands"].values()
    )


class CrazyEights:
    id = "crazy-eights"
    name = "Crazy Eights"
    min_players = 2
    max_players = 4

    # -- state lifecycle --

    def initial_state(self, players: list[str]) -> dict[str, Any]:
        deck = _full_deck()
        random.shuffle(deck)
        hands: dict[str, list[str]] = {}
        for p in players:
            hands[p] = deck[:DEAL_COUNT]
            deck = deck[DEAL_COUNT:]
        while _is_eight(deck[-1]):
            deck.insert(0, deck.pop())
        starter = deck.pop()
        return {
            "deck": deck,
            "discard": [starter],
            "hands": hands,
            "order": list(players),
            "turn_player": players[0],
            "current_suit": _suit(starter),
            "winner": None,
            "card_counts": _counts(hands),
        }

    def apply_action(
        self, state: dict[str, Any], player: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if state["winner"] is not None:
            raise IllegalAction("game is over")
        if state["turn_player"] != player:
            raise IllegalAction("not your turn")

        hand = state["hands"][player]
        total_slots = len(hand) + 1
        raw_index = action.get("index")
        if not isinstance(raw_index, int):
            raise IllegalAction("missing index")
        index = raw_index % total_slots if total_slots > 0 else 0

        if index >= len(hand):
            return self._apply_draw(state, player)
        return self._apply_play(state, player, index, action.get("chosen_suit"))

    def _apply_play(
        self,
        state: dict[str, Any],
        player: str,
        index: int,
        chosen_suit: str | None,
    ) -> dict[str, Any]:
        hand = list(state["hands"][player])
        card = hand[index]
        top = state["discard"][-1]

        if _is_eight(card):
            if chosen_suit not in SUITS:
                raise IllegalAction("must choose a suit when playing an 8")
            new_suit = chosen_suit
        elif not _can_play(card, state["current_suit"], _rank(top)):
            raise IllegalAction("card doesn't match suit or rank")
        else:
            new_suit = _suit(card)

        hand.pop(index)
        new_hands = {**state["hands"], player: hand}
        new_discard = state["discard"] + [card]
        winner: str | None = player if not hand else None

        new_state: dict[str, Any] = {
            **state,
            "discard": new_discard,
            "hands": new_hands,
            "current_suit": new_suit,
            "turn_player": _next_player(state["order"], player),
            "winner": winner,
            "card_counts": _counts(new_hands),
        }

        if winner is None:
            new_state = self._maybe_draw_game(new_state)
        return new_state

    def _apply_draw(self, state: dict[str, Any], player: str) -> dict[str, Any]:
        deck = list(state["deck"])
        discard = list(state["discard"])

        if not deck:
            if len(discard) <= 1:
                raise IllegalAction("no cards left to draw")
            top = discard[-1]
            deck = discard[:-1]
            random.shuffle(deck)
            discard = [top]

        card = deck.pop()
        hand = list(state["hands"][player]) + [card]
        new_hands = {**state["hands"], player: hand}

        new_state: dict[str, Any] = {
            **state,
            "deck": deck,
            "discard": discard,
            "hands": new_hands,
            "turn_player": _next_player(state["order"], player),
            "card_counts": _counts(new_hands),
        }
        return self._maybe_draw_game(new_state)

    def _maybe_draw_game(self, state: dict[str, Any]) -> dict[str, Any]:
        if state["deck"] or _anyone_can_play(state):
            return state
        reshuffleable = len(state["discard"]) - 1
        if reshuffleable > 0:
            return state
        state = {**state, "winner": "draw"}
        return state

    # -- protocol queries --

    def current_player(self, state: dict[str, Any]) -> str | None:
        if self.is_terminal(state):
            return None
        return state["turn_player"]

    def winner(self, state: dict[str, Any]) -> str | None:
        w = state.get("winner")
        if w == "draw":
            return None
        return w

    def is_terminal(self, state: dict[str, Any]) -> bool:
        return state.get("winner") is not None

    # -- cursor model --

    def initial_cursor(self) -> dict[str, Any]:
        return {"index": 0, "phase": "hand", "suit_index": 0}

    def move_cursor(self, cursor: dict[str, Any], dr: int, dc: int) -> dict[str, Any]:
        if cursor["phase"] == "suit":
            return {**cursor, "suit_index": (cursor["suit_index"] + dc) % len(SUITS)}
        return {**cursor, "index": cursor["index"] + dc}

    def cursor_action(self, cursor: dict[str, Any]) -> dict[str, Any]:
        if cursor["phase"] == "suit":
            return {
                "type": "play",
                "index": cursor["index"],
                "chosen_suit": SUITS[cursor["suit_index"]],
            }
        return {"type": "play", "index": cursor["index"]}

    def prepare_action(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any] | None:
        if cursor["phase"] == "suit":
            return None

        me = state["turn_player"]
        hand = state["hands"][me]
        total_slots = len(hand) + 1
        index = cursor["index"] % total_slots if total_slots > 0 else 0

        if index >= len(hand):
            return None

        if _is_eight(hand[index]):
            return {**cursor, "index": index, "phase": "suit", "suit_index": 0}
        return None

    def sync_cursor(
        self, cursor: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        return {**cursor, "phase": "hand", "suit_index": 0}

    # -- animation --

    def animation_for(
        self, prev_state: dict[str, Any], new_state: dict[str, Any]
    ) -> None:
        return None

    # -- rendering --

    def render(
        self,
        state: dict[str, Any],
        viewport: Size,
        ui: dict[str, Any] | None = None,
    ) -> list[Strip]:
        ui = ui or {}
        theme = ui.get("theme")
        me = ui.get("player")
        cursor = ui.get("cursor", {})
        active = ui.get("active", False) and not self.is_terminal(state)
        cursor_active, cursor_inactive = cursor_palette(theme)
        hdr_style = header_palette(theme)
        muted = style(theme, "muted")
        grid_sty = style(theme, "primary")

        lines: list[Strip] = []

        # order header with card counts
        lines.append(order_header(state, hdr_style, marks_key="card_counts"))
        lines.append(Strip.blank(0))

        # discard pile
        top_card = state["discard"][-1]
        tg = _card_glyph(top_card)
        ts = _card_style(top_card, theme)
        lines.append(Strip([Segment("        ┌────┐", grid_sty)]))
        lines.append(
            Strip(
                [
                    Segment("        │ ", grid_sty),
                    Segment(tg, ts),
                    Segment(" │", grid_sty),
                ]
            )
        )
        lines.append(Strip([Segment("        └────┘", grid_sty)]))

        # suit + deck info
        sg = SUIT_GLYPHS[state["current_suit"]]
        if state["current_suit"] in RED_SUITS:
            ss = style(theme, "error", bold=True)
        else:
            ss = style(theme, "foreground", bold=True)
        deck_count = len(state["deck"])
        lines.append(
            Strip(
                [
                    Segment("     Suit: ", muted),
                    Segment(sg, ss),
                    Segment(f"   Deck: {deck_count}", muted),
                ]
            )
        )
        lines.append(Strip.blank(0))

        # player's hand
        if me and me in state.get("hands", {}):
            hand = state["hands"][me]
            total_slots = max(len(hand) + 1, 1)
            phase = cursor.get("phase", "hand")
            cursor_pos = cursor.get("index", 0) % total_slots

            segs: list[Segment] = [Segment("  ")]
            for i, card in enumerate(hand):
                glyph = _card_glyph(card)
                if i == cursor_pos and phase == "hand":
                    bg = cursor_active if active else cursor_inactive
                    segs.extend(cursor_bracket(glyph, bg))
                else:
                    segs.extend(
                        [
                            Segment(" "),
                            Segment(glyph, _card_style(card, theme)),
                            Segment(" "),
                        ]
                    )
                segs.append(Segment(" "))

            if cursor_pos == len(hand) and phase == "hand":
                bg = cursor_active if active else cursor_inactive
                segs.extend(cursor_bracket("Draw", bg))
            else:
                segs.extend([Segment(" "), Segment("Draw", muted), Segment(" ")])
            lines.append(Strip(segs))
        else:
            lines.append(Strip([Segment("  (spectating)", muted)]))

        # suit picker or blank
        if me and cursor.get("phase") == "suit":
            suit_segs: list[Segment] = [Segment("  Choose suit:  ", muted)]
            si = cursor.get("suit_index", 0)
            for i, s in enumerate(SUITS):
                g = SUIT_GLYPHS[s]
                if i == si:
                    bg = cursor_active if active else cursor_inactive
                    suit_segs.extend(cursor_bracket(g, bg))
                else:
                    c = (
                        style(theme, "error", bold=True)
                        if s in RED_SUITS
                        else style(theme, "foreground", bold=True)
                    )
                    suit_segs.extend([Segment(" "), Segment(g, c), Segment(" ")])
                suit_segs.append(Segment(" "))
            lines.append(Strip(suit_segs))
        else:
            lines.append(Strip.blank(0))

        # status
        w = state.get("winner")
        if w == "draw":
            lines.append(status_strip("  No one can play — draw!"))
        elif w:
            lines.append(status_strip(f"  {w} wins!"))
        elif cursor.get("phase") == "suit":
            lines.append(status_strip("  Choose a suit for your 8"))
        elif state["turn_player"] == me:
            lines.append(status_strip("  Play a card or draw"))
        else:
            lines.append(status_strip(f"  Waiting for {state['turn_player']}…"))

        return lines

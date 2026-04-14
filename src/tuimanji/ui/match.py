from typing import TYPE_CHECKING, Any, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from .. import store
from ..db import engine_for
from ..engine import Animation, GameError, NotYourTurn
from ..games import get as get_game
from .canvas import GameCanvas
from .theme import palette_from_app

if TYPE_CHECKING:
    from textual.timer import Timer

    from ..app import TuimanjiApp


class MatchScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Lobby"),
        Binding("up", "move(-1,0)", "Up"),
        Binding("down", "move(1,0)", "Down"),
        Binding("left", "move(0,-1)", "Left"),
        Binding("right", "move(0,1)", "Right"),
        Binding("enter", "place", "Place"),
        Binding("r", "rotate", "Rotate", show=False),
        Binding("space", "stage", "Stage", show=False),
    ]

    CSS = """
    MatchScreen { align: center top; }
    MatchScreen > Vertical { width: 100%; height: 1fr; }
    MatchScreen > Vertical > Horizontal { width: 1fr; height: 1fr; }
    #error { height: 1; padding: 0 2; color: $error; }
    GameCanvas { border: round $primary; width: 1fr; height: 1fr; }
    """

    def __init__(self, game_id: str, match_id: str) -> None:
        super().__init__()
        self.game_id = game_id
        self.match_id = match_id
        self.game = get_game(game_id)
        self.engine = engine_for(game_id)
        self.canvas: GameCanvas | None = None
        self._cursor: dict[str, Any] = self.game.initial_cursor()
        self._last_turn = -1
        self._last_active: bool | None = None
        self._displayed_state: dict[str, Any] | None = None
        self._animation_timer: "Timer | None" = None
        self._animation: Animation | None = None
        self._frame: int = 0
        self._pending_state: dict[str, Any] | None = None
        self._error_label: Static | None = None
        self._palette: dict[str, str] | None = None

    @property
    def _app(self) -> "TuimanjiApp":
        return cast("TuimanjiApp", self.app)

    @property
    def me(self) -> str:
        return self._app.player_id

    @property
    def _animating(self) -> bool:
        return self._animation_timer is not None

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                latest = store.latest_state(self.engine, self.match_id)
                if latest is None:
                    raise RuntimeError(
                        f"MatchScreen opened for un-started match {self.match_id}"
                    )
                self._displayed_state = latest.state
                self._last_turn = latest.turn
                self.canvas = GameCanvas(self.game, latest.state)
                yield self.canvas
            self._error_label = Static("", id="error")
            yield self._error_label
        yield Footer()

    def on_mount(self) -> None:
        self._push_cursor_ui()
        self._refresh()
        self.set_interval(0.5, self._refresh)
        self.watch(self.app, "theme", self._on_theme_changed, init=False)

    def _on_theme_changed(self, _theme_name: str) -> None:
        self._palette = palette_from_app(self.app)
        self._push_cursor_ui()

    def _push_cursor_ui(self, active: bool | None = None) -> None:
        if self.canvas is None:
            return
        if active is None:
            active = self._last_active if self._last_active is not None else True
        if self._palette is None:
            self._palette = palette_from_app(self.app)
        self.canvas.set_ui(
            cursor=self._cursor,
            active=active,
            player=self.me,
            theme=self._palette,
        )

    def _refresh(self) -> None:
        if self._animating:
            return
        latest = store.latest_state(self.engine, self.match_id)
        if latest is None:
            return
        if latest.turn != self._last_turn:
            self._consume_new_turn(latest.state)
            self._last_turn = latest.turn
        my_turn = latest.current == self.me and not self.game.is_terminal(latest.state)
        if my_turn != self._last_active:
            self._last_active = my_turn
            self._push_cursor_ui(active=my_turn)

    def _consume_new_turn(self, new_state: dict[str, Any]) -> None:
        prev = self._displayed_state
        if prev is None:
            self._set_displayed(new_state)
            self._maybe_sync_cursor(new_state)
            return
        anim = self.game.animation_for(prev, new_state)
        if anim is None:
            self._set_displayed(new_state)
            self._maybe_sync_cursor(new_state)
            return
        # Start animation: canvas keeps showing prev, we overlay frames.
        self._pending_state = new_state
        self._start_animation(anim)

    def _maybe_sync_cursor(self, state: dict[str, Any]) -> None:
        sync = getattr(self.game, "sync_cursor", None)
        if sync is None:
            return
        new_cursor = sync(self._cursor, state)
        if new_cursor is not self._cursor:
            self._cursor = new_cursor
            self._push_cursor_ui()

    def _set_displayed(self, state: dict[str, Any]) -> None:
        self._displayed_state = state
        if self.canvas is not None:
            self.canvas.set_state(state)

    def _start_animation(self, anim: Animation) -> None:
        self._animation = anim
        self._frame = 0
        if self.canvas is not None:
            self.canvas.set_ui(animation=anim.overlay(0))
        self._animation_timer = self.set_interval(anim.interval, self._tick_animation)

    def _tick_animation(self) -> None:
        if self._animation is None:
            return
        self._frame += 1
        if self._frame >= self._animation.frames:
            self._finish_animation()
            return
        if self.canvas is not None:
            self.canvas.set_ui(animation=self._animation.overlay(self._frame))

    def _finish_animation(self) -> None:
        if self._animation_timer is not None:
            self._animation_timer.stop()
            self._animation_timer = None
        self._animation = None
        if self.canvas is not None:
            self.canvas.set_ui(animation=None)
        if self._pending_state is not None:
            self._set_displayed(self._pending_state)
            self._maybe_sync_cursor(self._pending_state)
            self._pending_state = None
        self._refresh()

    def on_unmount(self) -> None:
        if self._animation_timer is not None:
            self._animation_timer.stop()
            self._animation_timer = None
        self._animation = None

    def action_move(self, dr: int, dc: int) -> None:
        if self._animating:
            return
        self._cursor = self.game.move_cursor(self._cursor, dr, dc)
        self._push_cursor_ui()

    def action_place(self) -> None:
        if self._animating:
            return
        try:
            store.submit_action(
                self.engine,
                self.match_id,
                self.me,
                self.game.cursor_action(self._cursor),
                self.game,
            )
            if self._error_label:
                self._error_label.update("")
        except NotYourTurn:
            if self._error_label:
                self._error_label.update("not your turn")
            return
        except GameError as e:
            if self._error_label:
                self._error_label.update(str(e))
            return
        # Drive the animation immediately from the local write rather than
        # waiting for the poll — gives the dropping player instant feedback.
        self._refresh()

    def action_rotate(self) -> None:
        if self._animating:
            return
        rotate = getattr(self.game, "rotate_cursor", None)
        if rotate is None:
            return
        self._cursor = rotate(self._cursor)
        self._push_cursor_ui()

    def action_stage(self) -> None:
        if self._animating:
            return
        stage = getattr(self.game, "stage_cursor", None)
        if stage is None:
            return
        try:
            self._cursor = stage(self._cursor)
            if self._error_label:
                self._error_label.update("")
        except GameError as e:
            if self._error_label:
                self._error_label.update(str(e))
            return
        self._push_cursor_ui()

    def action_back(self) -> None:
        self.app.pop_screen()

"""Waiting room: host can cancel a not-yet-started match; non-hosts can't."""

from typing import cast

import pytest

from tuimanji import store
from tuimanji.app import TuimanjiApp
from tuimanji.db import _reset_engine
from tuimanji.games import REGISTRY
from tuimanji.ui.waiting import WaitingRoomScreen


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIMANJI_DB", str(tmp_path))
    _reset_engine()
    return tmp_path


@pytest.mark.asyncio
async def test_host_can_cancel(fresh_db):
    app = TuimanjiApp(new_game_id="chess")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = cast(WaitingRoomScreen, app.screen)
        assert isinstance(screen, WaitingRoomScreen)
        match_id = screen.match_id
        assert store.get_match(match_id) is not None

        await pilot.press("c")
        await pilot.pause()

        assert store.get_match(match_id) is None
        # Cancel pops back to whatever was below — the lobby in this case.
        assert not isinstance(app.screen, WaitingRoomScreen)


@pytest.mark.asyncio
async def test_non_host_cannot_cancel(fresh_db):
    # Host is some other player; we sit as the joining party.
    chess = REGISTRY["chess"]
    match_id = store.create_match(chess, "carol")
    app = TuimanjiApp(join_match_id=match_id)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = cast(WaitingRoomScreen, app.screen)
        assert isinstance(screen, WaitingRoomScreen)

        await pilot.press("c")
        await pilot.pause()

        assert store.get_match(match_id) is not None
        assert isinstance(app.screen, WaitingRoomScreen)

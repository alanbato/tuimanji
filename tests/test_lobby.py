"""Lobby UX: arrow-key navigation should re-target the matches table."""

from typing import cast

import pytest

from tuimanji import store
from tuimanji.app import TuimanjiApp
from tuimanji.db import _reset_engine
from tuimanji.games import REGISTRY
from tuimanji.ui.lobby import LobbyScreen


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIMANJI_DB", str(tmp_path))
    _reset_engine()
    return tmp_path


@pytest.mark.asyncio
async def test_arrowing_to_chess_swaps_matches_pane(fresh_db):
    ttt_id = store.create_match(REGISTRY["tic-tac-toe"], "alice")
    chess_id = store.create_match(REGISTRY["chess"], "alice")

    app = TuimanjiApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = cast(LobbyScreen, app.screen)
        assert screen.selected_game_id == "tic-tac-toe"
        assert ttt_id in screen._match_ids
        assert chess_id not in screen._match_ids

        # Registry order: tic-tac-toe, connect-4, battleship, reversi, chess.
        for _ in range(4):
            await pilot.press("down")
        await pilot.pause()

        assert screen.selected_game_id == "chess", (
            f"expected chess after 4 downs, got {screen.selected_game_id}"
        )
        assert chess_id in screen._match_ids
        assert ttt_id not in screen._match_ids

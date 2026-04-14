"""Shared helpers used across game implementations.

Pure-function helpers only — no I/O, no DB. Anything that's been copy-pasted
between two or more games lives here so the games themselves stay focused on
their own rules and rendering.
"""

from typing import Any

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip

from ..ui.theme import bg_style, style

EMPTY = "."


def empty_grid(rows: int, cols: int, fill: str = EMPTY) -> list[list[str]]:
    return [[fill] * cols for _ in range(rows)]


def copy_grid(grid: list[list[str]]) -> list[list[str]]:
    return [row[:] for row in grid]


def in_bounds(r: int, c: int, rows: int, cols: int) -> bool:
    return 0 <= r < rows and 0 <= c < cols


def opponent_of(order: list[str], player: str) -> str:
    return order[(order.index(player) + 1) % len(order)]


def wrap_cursor(
    cursor: dict[str, Any], dr: int, dc: int, rows: int, cols: int
) -> dict[str, Any]:
    return {
        **cursor,
        "row": (cursor["row"] + dr) % rows,
        "col": (cursor["col"] + dc) % cols,
    }


def grid_top(cols: int, s: Style) -> Strip:
    return Strip([Segment("┌" + "───┬" * (cols - 1) + "───┐", s)])


def grid_sep(cols: int, s: Style) -> Strip:
    return Strip([Segment("├" + "───┼" * (cols - 1) + "───┤", s)])


def grid_bot(cols: int, s: Style) -> Strip:
    return Strip([Segment("└" + "───┴" * (cols - 1) + "───┘", s)])


def col_labels(cols: int, s: Style, start: int = 0) -> Strip:
    segs: list[Segment] = [Segment(" ")]
    for c in range(cols):
        segs.append(Segment(" "))
        segs.append(Segment(str(start + c), s))
        segs.append(Segment(" "))
        segs.append(Segment(" "))
    return Strip(segs)


def cell_segments(glyph: str, s: Style) -> list[Segment]:
    return [Segment(" "), Segment(glyph, s), Segment(" ")]


def cursor_bracket(glyph: str, bg: Style) -> list[Segment]:
    return [Segment("[", bg), Segment(glyph, bg), Segment("]", bg)]


def cursor_palette(theme: dict[str, Any] | None) -> tuple[Style, Style]:
    """Standard (active, inactive) background-highlighted cursor styles."""
    return (
        bg_style(theme, "warning", color="black", bold=True),
        bg_style(theme, "muted", color="white"),
    )


def order_header(
    state: dict[str, Any],
    header_style: Style,
    marks_key: str = "marks",
) -> Strip:
    marks = state.get(marks_key, {}) or {}
    text = "  "
    for p in state.get("order", []):
        tag = marks.get(p)
        text += f"{p}({tag})  " if tag is not None else f"{p}  "
    return Strip([Segment(text, header_style)])


def status_strip(text: str) -> Strip:
    return Strip([Segment(text, Style(italic=True))])


def header_palette(theme: dict[str, Any] | None) -> Style:
    return style(theme, "muted", dim=True)

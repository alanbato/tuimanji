"""Bridge Textual's reactive theme variables into game render styles.

Games render via Rich `Segment` + `Style`, which can't read Textual CSS variables
directly. `MatchScreen` builds a small semantic palette dict from
`App.theme_variables` and passes it through `ui["theme"]`; games use `style()` to
build Rich styles that fall back gracefully when the dict is absent (e.g. tests).
"""

from typing import Any

from rich.style import Style
from textual.app import App

# Semantic keys games may consume. Names match Textual's CSS variables where
# possible so the mapping stays obvious.
_KEYS = (
    "primary",
    "accent",
    "success",
    "warning",
    "error",
    "foreground",
    "muted",
    "background",
    "surface",
)

# Last-ditch fallbacks if the theme dict is missing or doesn't define a key.
_FALLBACKS: dict[str, str] = {
    "primary": "bright_cyan",
    "accent": "bright_magenta",
    "success": "bright_green",
    "warning": "bright_yellow",
    "error": "bright_red",
    "foreground": "white",
    "muted": "grey50",
    "background": "black",
    "surface": "grey15",
}


def _strip_alpha(hex_color: str) -> str:
    """Rich Style rejects #RRGGBBAA; drop the alpha byte if present."""
    if hex_color.startswith("#") and len(hex_color) == 9:
        return hex_color[:7]
    return hex_color


def palette_from_app(app: App) -> dict[str, str]:
    """Snapshot the active Textual theme into a flat semantic palette."""
    tv = app.theme_variables
    palette: dict[str, str] = {}
    for key in _KEYS:
        # `foreground-muted` is the textual CSS name; we expose it as `muted`.
        source = "foreground-muted" if key == "muted" else key
        raw = tv.get(source)
        palette[key] = _strip_alpha(raw) if raw else _FALLBACKS[key]
    return palette


def _resolve(theme: dict[str, Any] | None, key: str) -> str | None:
    raw = (theme or {}).get(key) or _FALLBACKS.get(key)
    return _strip_alpha(raw) if raw else None


def contrast_style(theme: dict[str, Any] | None, bg_key: str, **kwargs: Any) -> Style:
    """Pick a foreground color that contrasts with the theme's `bg_key`.

    Uses Textual's `Color.get_contrast_text` so labels stay legible against
    whichever theme is active. Falls back to a plain Style when the color
    can't be parsed (tests, bad input).
    """
    raw = _resolve(theme, bg_key)
    if raw is None:
        return Style(**kwargs)
    return contrast_on_hex(raw, **kwargs)


def contrast_on_hex(bg_hex: str, **kwargs: Any) -> Style:
    """Like `contrast_style` but against an explicit hex (use for computed bgs)."""
    from textual.color import Color as TextualColor

    try:
        fg = TextualColor.parse(bg_hex).get_contrast_text()
    except Exception:
        return Style(**kwargs)
    return Style(color=_strip_alpha(fg.hex), **kwargs)


def shifted_color(theme: dict[str, Any] | None, key: str, delta: float) -> str:
    """Return `theme[key]`'s hex with luminance shifted by `delta`.

    Positive `delta` lightens, negative darkens. Used to derive paired
    foreground/background shades (e.g. dark vs light checker squares) from
    a single theme semantic, so the result tracks the active theme instead
    of inverting on light themes the way text colors do.
    """
    from textual.color import Color as TextualColor

    raw = _resolve(theme, key) or "#808080"
    try:
        c = TextualColor.parse(raw)
    except Exception:
        return raw
    shifted = c.lighten(delta) if delta >= 0 else c.darken(-delta)
    return _strip_alpha(shifted.hex)


def style(theme: dict[str, Any] | None, key: str, **kwargs: Any) -> Style:
    """Build a Rich Style with a color drawn from the theme palette.

    Falls back to `_FALLBACKS[key]` when `theme` is None or the key is missing,
    so games stay renderable in tests and in pre-theme code paths.
    """
    color = (theme or {}).get(key) or _FALLBACKS.get(key)
    return Style(color=color, **kwargs)


def bg_style(theme: dict[str, Any] | None, key: str, **kwargs: Any) -> Style:
    """Same as `style` but applies the color as a background."""
    color = (theme or {}).get(key) or _FALLBACKS.get(key)
    return Style(bgcolor=color, **kwargs)

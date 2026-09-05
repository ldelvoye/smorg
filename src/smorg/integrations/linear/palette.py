"""Linear's brand indigo, picked against the terminal background."""

from __future__ import annotations

from smorg.shell.terminal_palette import relative_luminance

# Linear's published pair (linear.app/brand): the brand indigo, and their lighter tint for
# dark surfaces.
_INDIGO_DARK = "#828fff"
_INDIGO_LIGHT = "#5e6ad2"


def accent_for_background(background: tuple[int, int, int] | None) -> str:
    if background is None:
        return _INDIGO_DARK
    if relative_luminance(background) > 0.5:
        return _INDIGO_LIGHT
    return _INDIGO_DARK

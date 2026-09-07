"""Linear's brand indigo, picked against the terminal background."""

from __future__ import annotations

from smorg.shell.terminal_palette import pick_for_background

# Linear's published pair (linear.app/brand): the brand indigo, and their lighter tint for
# dark surfaces.
_INDIGO_DARK = "#828fff"
_INDIGO_LIGHT = "#5e6ad2"


def accent_for_background(background: tuple[int, int, int] | None) -> str:
    return pick_for_background(_INDIGO_DARK, _INDIGO_LIGHT, background)

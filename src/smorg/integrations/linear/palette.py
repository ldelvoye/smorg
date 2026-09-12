"""Linear's brand indigo, picked against the terminal background."""

from __future__ import annotations

from dataclasses import dataclass

from smorg.shell.terminal_palette import pick_for_background

# Linear's published pair (linear.app/brand): the brand indigo, and their lighter tint for
# dark surfaces.
_INDIGO_DARK = "#828fff"
_INDIGO_LIGHT = "#5e6ad2"


def accent_for_background(background: tuple[int, int, int] | None) -> str:
    return pick_for_background(_INDIGO_DARK, _INDIGO_LIGHT, background)


@dataclass(frozen=True)
class Glow:
    """The three brightnesses the mark and the sky are drawn in."""

    rest: str
    lit: str
    dim: str


# The lit shade is a real colour step, not bold alone: bold braille reads the same on a light
# terminal.
_GLOW_DARK = Glow(rest=_INDIGO_DARK, lit="bold #b8bfff", dim=f"dim {_INDIGO_DARK}")
_GLOW_LIGHT = Glow(rest=_INDIGO_LIGHT, lit="bold #c4c9ff", dim=f"dim {_INDIGO_LIGHT}")


def glow_for_background(background: tuple[int, int, int] | None) -> Glow:
    return pick_for_background(_GLOW_DARK, _GLOW_LIGHT, background)

"""GitHub's contribution greens, picked against the terminal background."""

from __future__ import annotations

from smorg.shell.terminal_palette import pick_for_background

_GREEN_RAMP_DARK = ("#006d32", "#26a641", "#39d353", "#7ee787")
_GREEN_RAMP_LIGHT = ("#aceebb", "#4ac26b", "#1a7f37", "#044f1e")


def ramp_for_background(background: tuple[int, int, int] | None) -> tuple[str, str, str, str]:
    return pick_for_background(_GREEN_RAMP_DARK, _GREEN_RAMP_LIGHT, background)

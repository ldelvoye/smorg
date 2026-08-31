"""GitHub's contribution greens, picked against the terminal background."""

from __future__ import annotations

from smorg.shell.terminal_palette import relative_luminance

_GREEN_RAMP_DARK = ("#006d32", "#26a641", "#39d353", "#7ee787")
_GREEN_RAMP_LIGHT = ("#aceebb", "#4ac26b", "#1a7f37", "#044f1e")


def ramp_for_background(background: tuple[int, int, int] | None) -> tuple[str, str, str, str]:
    if background is None:
        return _GREEN_RAMP_DARK
    if relative_luminance(background) > 0.5:
        return _GREEN_RAMP_LIGHT
    return _GREEN_RAMP_DARK

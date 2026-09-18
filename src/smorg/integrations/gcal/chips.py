"""Filled event chips the way Google draws them, and the marker glyphs that ride on rows."""

from __future__ import annotations

import math

from rich.text import Text

from smorg.integrations.gcal.palette import BREATH_SECONDS
from smorg.integrations.gcal.source import Event, Response
from smorg.shell.format import truncating
from smorg.shell.terminal_palette import relative_luminance

FALLBACK_COLOR = "#616161"
MEET_GLYPH = "▶"
RECURRING_GLYPH = "⟲"
_RSVP_GLYPHS = {
    Response.ACCEPTED: "●",
    Response.TENTATIVE: "◐",
    Response.NEEDS_ACTION: "○",
    Response.DECLINED: "✗",
    Response.NONE: "",
}
_LIGHT_TEXT_BELOW = 0.4
_PULSE_LIFT = 0.35


def _rgb(color: str) -> tuple[int, int, int]:
    digits = color.lstrip("#")
    if len(digits) != 6:
        digits = "616161"
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def _text_color(color: str) -> str:
    rgb = _rgb(color)
    if relative_luminance(rgb) < _LIGHT_TEXT_BELOW:
        return "white"
    return "black"


def chip_style(color: str) -> str:
    """Contrast text on the calendar colour: black on light chips, white on dark ones."""
    text_color = _text_color(color)
    return f"{text_color} on {color}"


def pulsed_fill(color: str, elapsed: float) -> str:
    """The calendar colour lifted toward white by up to `_PULSE_LIFT`, on the breathing wave."""
    phase = (elapsed / BREATH_SECONDS) % 1.0
    brightness = 0.5 + 0.5 * math.cos(2 * math.pi * phase)
    lift = _PULSE_LIFT * brightness
    red, green, blue = _rgb(color)
    r = round(red + (255 - red) * lift)
    g = round(green + (255 - green) * lift)
    b = round(blue + (255 - blue) * lift)
    return f"#{r:02x}{g:02x}{b:02x}"


def format_chip(
    text: str,
    width: int,
    color: str,
    selected: bool,
    past: bool,
    fill: str | None = None,
) -> Text:
    if selected and fill is not None:
        text_color = _text_color(color)
        style = f"bold {text_color} on {fill}"
    else:
        style = chip_style(color)
        if selected:
            style = f"bold {style}"
        if past:
            style = f"dim {style}"
    chip = Text(f" {text}", style=style)
    chip.truncate(max(1, width), overflow="ellipsis", pad=True)
    return chip


def rsvp_glyph(response: Response) -> str:
    return _RSVP_GLYPHS[response]


def format_markers(event: Event) -> Text:
    """ "▶ ○ ⟲" for a recurring Meet invite awaiting a reply; blank pieces are dropped."""
    pieces: list[str] = []
    if event.meet_url:
        pieces.append(MEET_GLYPH)
    glyph = rsvp_glyph(event.my_response)
    if glyph:
        pieces.append(glyph)
    if event.recurring:
        pieces.append(RECURRING_GLYPH)
    joined = " ".join(pieces)
    markers = Text(joined, style="dim")
    return truncating(markers)

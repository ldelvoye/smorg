"""Filled event chips the way Google draws them, and the marker glyphs that ride on rows."""

from __future__ import annotations

from rich.text import Text

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


def _rgb(color: str) -> tuple[int, int, int]:
    digits = color.lstrip("#")
    if len(digits) != 6:
        digits = "616161"
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def chip_style(color: str) -> str:
    """Contrast text on the calendar colour: black on light chips, white on dark ones."""
    rgb = _rgb(color)
    if relative_luminance(rgb) < _LIGHT_TEXT_BELOW:
        return f"white on {color}"
    return f"black on {color}"


def format_chip(text: str, width: int, color: str, selected: bool, past: bool) -> Text:
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

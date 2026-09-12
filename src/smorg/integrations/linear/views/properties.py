"""Property-row glyphs and formatting shared by the Linear pages."""

from __future__ import annotations

from rich.text import Text

from smorg.shell.format import truncating

GLYPH_ASSIGNEE = "@"
GLYPH_DUE = "◷"
GLYPH_LINK = "↗"


def format_property_row(glyph: str, glyph_style: str, value: str, value_style: str = "") -> Text:
    row = Text()
    row.append(glyph, style=glyph_style)
    row.append(" ")
    row.append(value, style=value_style)
    return truncating(row)


def join_inline(rows: list[Text]) -> Text:
    line = Text()
    for index, row in enumerate(rows):
        if index > 0:
            line.append(" · ", style="dim")
        row.no_wrap = False
        line.append_text(row)
    return line

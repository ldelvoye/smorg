"""Shared marks and card helpers for designed integration views."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel as Card
from rich.text import Text

from smorg.shell.format import SELECTED_STYLE, truncating

SELECTED_MARK = "▸"
CHANGED_MARK = "●"
CARD_BORDER_STYLE = "dim"
# Card titles sit on the dim border; "not dim" stops the border's dim washing their color.
CARD_TITLE_STYLE = "bold not dim"
CARD_CHROME = 4
"""The columns a card's border and padding take from the width its body has."""
_MARKED_CELL_INDENT = " " * 4


def format_card(title: Text, body: list[RenderableType]) -> Card:
    return Card(
        Group(*body),
        title=title,
        title_align="left",
        box=box.ROUNDED,
        border_style=CARD_BORDER_STYLE,
        padding=(0, 1),
    )


def format_count(count: int, noun: str) -> str:
    if count == 1:
        return f"1 {noun}"
    return f"{count} {noun}s"


def format_box(body: list[RenderableType]) -> Card:
    """A titleless rounded card, for a column whose sections name themselves."""
    return Card(Group(*body), box=box.ROUNDED, border_style=CARD_BORDER_STYLE, padding=(0, 1))


def format_card_title(label: str, color: str = "") -> Text:
    """A card title in the shared bold style, tinted `color` when one is given."""
    if color:
        style = f"{CARD_TITLE_STYLE} {color}"
    else:
        style = CARD_TITLE_STYLE
    return Text(label, style=style)


def format_marks(selected: bool, changed: bool, changed_style: str) -> Text:
    """The two-cell mark column: the selection cursor, then the unseen-change dot."""
    marks = Text()
    if selected:
        marks.append(SELECTED_MARK, style=SELECTED_STYLE)
    else:
        marks.append(" ")
    marks.append(" ")
    if changed:
        marks.append(CHANGED_MARK, style=changed_style)
    else:
        marks.append(" ")
    return marks


def format_marked_cell(
    title: str, meta: str, selected: bool, changed: bool, changed_style: str
) -> tuple[Text, Text]:
    """A list entry's two lines: the marked title, bold when selected, then its dim meta."""
    head = format_marks(selected, changed, changed_style)
    head.append(" ")
    if selected:
        head.append(title, style="bold")
    else:
        head.append(title)
    meta_line = Text(_MARKED_CELL_INDENT)
    meta_line.append(meta, style="dim")
    return truncating(head), truncating(meta_line)

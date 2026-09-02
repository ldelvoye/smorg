"""Shared marks and card helpers for designed integration views."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel as Card
from rich.text import Text

SELECTED_MARK = "▸"
CHANGED_MARK = "●"
CARD_BORDER_STYLE = "dim"
# Card titles sit on the dim border; "not dim" stops the border's dim washing their color.
CARD_TITLE_STYLE = "bold not dim"


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

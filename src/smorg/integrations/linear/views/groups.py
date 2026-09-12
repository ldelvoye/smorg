"""Status runs and their card titles, shared by the Linear lists."""

from __future__ import annotations

from typing import Protocol

from rich.text import Text

from smorg.integrations.linear.glyphs import status_color
from smorg.shell.cards import format_card_title
from smorg.shell.terminal_palette import StatusColors


class Statused(Protocol):
    @property
    def status(self) -> str: ...
    @property
    def status_type(self) -> str: ...


def status_runs[T: Statused](items: tuple[T, ...]) -> list[tuple[str, str, list[T]]]:
    """Runs of consecutive same-status items, in the order the caller already sorted them into."""
    groups: list[tuple[str, str, list[T]]] = []
    current_status = ""
    current_members: list[T] = []
    for item in items:
        if item.status != current_status:
            current_status = item.status
            current_members = []
            groups.append((item.status, item.status_type, current_members))
        current_members.append(item)
    return groups


def format_group_title(
    glyph: str, status: str, status_type: str, count: int, colors: StatusColors, accent: str
) -> Text:
    """A status group's card title: the glyph, the status and the count, tinted by stage."""
    color = status_color(status, status_type, colors, accent)
    if color == "dim":
        tint = ""
    else:
        tint = color
    return format_card_title(f"{glyph} {status} ({count})", tint)

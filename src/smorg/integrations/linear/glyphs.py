"""Linear's status discs, colors, ranks, progress bar and priority icon, shared by the views."""

from __future__ import annotations

from rich.text import Text

from smorg.shell.terminal_palette import StatusColors

DISC_IN_PROGRESS = "◐"
DISC_IN_REVIEW = "◕"
DISC_TODO = "○"
DISC_BLOCKED = "⊘"
DISC_DONE = "●"
DISC_BACKLOG = "◌"

PRIORITY_WIDTH = 3

BAR_CELLS = 10
_BAR_DONE = "▰"
_BAR_REST = "▱"

_PRIORITY_RANKS = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

# Ordered by actionability: doing, shepherding, queued, stuck.
_STATUS_RANKS = {"in progress": 0, "in review": 1, "todo": 3, "blocked": 5}


def status_rank(status: str, status_type: str) -> int:
    known = _STATUS_RANKS.get(status.casefold())
    if known is not None:
        return known
    if status_type == "started":
        return 2
    return 4


def priority_rank(priority: str) -> int:
    known = _PRIORITY_RANKS.get(priority.casefold())
    if known is not None:
        return known
    return 4


def format_progress_bar(percent: int, accent: str) -> Text:
    """`percent` of the bar in the accent, the rest dim, rounded to the nearest cell, half up."""
    clamped = max(0, min(100, percent))
    scaled = clamped * BAR_CELLS / 100
    done = int(scaled + 0.5)
    rest = BAR_CELLS - done
    bar = Text()
    bar.append(_BAR_DONE * done, style=accent)
    bar.append(_BAR_REST * rest, style="dim")
    return bar


def status_disc(status: str, status_type: str) -> str:
    normalized = status.casefold()
    if normalized == "in progress":
        return DISC_IN_PROGRESS
    if normalized == "in review":
        return DISC_IN_REVIEW
    if normalized == "todo":
        return DISC_TODO
    if normalized == "blocked":
        return DISC_BLOCKED
    # Unknown labels fall back to the stable machine category.
    if status_type == "completed":
        return DISC_DONE
    if status_type == "canceled":
        return DISC_BLOCKED
    if status_type == "backlog":
        return DISC_BACKLOG
    if status_type == "started":
        return DISC_IN_PROGRESS
    return DISC_TODO


def status_color(status: str, status_type: str, colors: StatusColors, accent: str) -> str:
    normalized = status.casefold()
    if normalized == "in progress":
        return colors.yellow
    if normalized == "in review":
        return colors.green
    if normalized == "todo":
        return "dim"
    if normalized == "blocked":
        return colors.red
    if status_type == "started":
        return colors.yellow
    if status_type == "completed":
        return accent
    return "dim"


def format_priority(priority: str, colors: StatusColors, stage_color: str) -> Text:
    """Linear's priority icon: ascending bars filled to the level, dashes for none, [!] urgent."""
    if stage_color == "dim":
        # A dim fill would vanish against the dim unfilled bars, so a muted stage fills plain.
        fill = ""
    else:
        fill = stage_color
    if priority == "Urgent":
        return Text("[!]", style=f"bold {colors.red}")
    if priority == "High":
        return Text("▂▄▆", style=fill)
    if priority == "Medium":
        bars = Text("▂▄", style=fill)
        bars.append("▆", style="dim")
        return bars
    if priority == "Low":
        bars = Text("▂", style=fill)
        bars.append("▄▆", style="dim")
        return bars
    return Text("---", style="dim")

"""The landing: today's date in the icon, the next meeting's countdown, Google's dots breathing,
and the way into each view."""

from __future__ import annotations

import math
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.app import RenderResult
from textual.binding import Binding
from textual.widgets import Static

from smorg.integrations.gcal.palette import BRAND_DOTS, BREATH_FPS, BREATH_SECONDS, RED, TODAY_BLUE
from smorg.integrations.gcal.source import CALENDAR_HOME, Event, EventKind, Response
from smorg.integrations.gcal.views import CalendarView
from smorg.shell.animation import FrameClock
from smorg.shell.cards import CHANGED_MARK, SELECTED_MARK, format_count
from smorg.shell.cursor import step_cursor
from smorg.shell.format import plain_lines
from smorg.shell.panel import PanelState
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.gcal.panel import CalendarPanel

_ENTER_GLYPH = "⏎"
_COMPACT_MIN_COLUMNS = 100
_ICON_INNER_WIDTH = 16
_PIXEL = "██"
_BLANK_PIXEL = "  "
_DIGIT_GAP = "  "
_DIGIT_FONT: dict[str, tuple[str, str, str, str, str]] = {
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", "###", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", "..#", "..#", "..#"),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "###"),
}

_DOT_GLYPH = "●"


@dataclass(frozen=True)
class _Destination:
    label: str
    view: CalendarView


_DESTINATIONS = (
    _Destination("today", CalendarView.DAY),
    _Destination("week", CalendarView.WEEK),
    _Destination("invites awaiting your reply", CalendarView.INVITES),
    _Destination("upcoming", CalendarView.UPCOMING),
)


def next_meeting_label(event: Event, now: datetime) -> str:
    """ "in 48 min" today, "tomorrow · 09:00" the day after, "Thu · 09:00" beyond that."""
    clock = event.start.strftime("%H:%M")
    days_ahead = (event.start.date() - now.date()).days
    if days_ahead == 0:
        minutes = max(0, math.ceil((event.start - now).total_seconds() / 60))
        return f"in {minutes} min"
    if days_ahead == 1:
        return f"tomorrow · {clock}"
    weekday = event.start.strftime("%a")
    return f"{weekday} · {clock}"


def _digit_rows(digit: str) -> list[str]:
    rows: list[str] = []
    for font_row in _DIGIT_FONT[digit]:
        pixels: list[str] = []
        for character in font_row:
            if character == "#":
                pixels.append(_PIXEL)
            else:
                pixels.append(_BLANK_PIXEL)
        rows.append("".join(pixels))
    return rows


def _format_icon(day: int) -> list[Text]:
    number = f"{day:02d}"
    left_rows = _digit_rows(number[0])
    right_rows = _digit_rows(number[1])
    top = Text("╭", style="dim")
    top.append("─" * _ICON_INNER_WIDTH, style="dim")
    top.append("◥", style=f"bold {RED}")
    lines = [top]
    for left, right in zip(left_rows, right_rows, strict=True):
        row = Text("│", style="dim")
        row.append(f" {left}{_DIGIT_GAP}{right} ", style=f"bold {TODAY_BLUE}")
        row.append("│", style="dim")
        lines.append(row)
    bottom = Text("╰", style="dim")
    bottom.append("─" * _ICON_INNER_WIDTH, style="dim")
    bottom.append("╯", style="dim")
    lines.append(bottom)
    return lines


def _format_header(now: datetime) -> Text:
    line = Text(now.strftime("%A, %B %-d"), style="bold")
    line.append("  ·  ", style="dim")
    line.append(now.strftime("%H:%M"), style="dim")
    return line


def _format_countdown(event: Event | None, now: datetime) -> list[Text]:
    if event is None:
        return [Text("nothing scheduled", style="dim")]
    title = Text(event.title, style="bold")
    line = Text()
    line.append(f"{CHANGED_MARK} ", style=f"bold {RED}")
    line.append(next_meeting_label(event, now), style=f"bold {RED}")
    span = f"{event.start.strftime('%H:%M')}–{event.end.strftime('%H:%M')}"
    line.append(f"  ·  {span}", style="dim")
    if event.my_response is Response.NEEDS_ACTION:
        line.append("  ·  awaiting your reply", style=RED)
    return [title, line]


def _dot_style(index: int, elapsed: float) -> str:
    phase = (elapsed / BREATH_SECONDS + index / 4) % 1.0
    brightness = 0.5 + 0.5 * math.cos(2 * math.pi * phase)
    if brightness > 0.66:
        return "bold"
    if brightness > 0.33:
        return ""
    return "dim"


def _format_dots(elapsed: float) -> Text:
    row = Text()
    for index, color in enumerate(BRAND_DOTS):
        if index > 0:
            row.append("  ")
        brightness = _dot_style(index, elapsed)
        style = f"{brightness} {color}".strip()
        row.append(_DOT_GLYPH, style=style)
    return row


def _description_for(view: CalendarView, panel: CalendarPanel) -> str:
    today_events = [e for e in panel.events_on(panel.today()) if e.kind is EventKind.MEETING]
    today_count = len(today_events)
    week_events = [e for e in panel.events() if e.kind is EventKind.MEETING]
    week_count = len(week_events)
    if view is CalendarView.DAY:
        return f"{format_count(today_count, 'meeting')} today, hour by hour"
    if view is CalendarView.WEEK:
        return f"{format_count(week_count, 'meeting')} across the loaded weeks, side by side"
    if view is CalendarView.INVITES:
        return "just what still needs a yes, no, or maybe"
    return f"{format_count(week_count, 'meeting')} coming up, one line each"


def _format_destinations(panel: CalendarPanel, cursor: int, compact: bool) -> list[Text]:
    lines: list[Text] = []
    invite_count = len(panel.invites())
    for index, destination in enumerate(_DESTINATIONS):
        selected = index == cursor
        head = Text()
        if selected:
            head.append(f"{SELECTED_MARK} ", style="bold")
            head.append(destination.label, style="bold")
        else:
            head.append(f"  {destination.label}")
        if destination.view is CalendarView.INVITES:
            head.append(f" ({invite_count})", style=RED)
        if selected:
            head.append(f"    {_ENTER_GLYPH} to open", style="dim")
        lines.append(head)
        description = _description_for(destination.view, panel)
        lines.append(Text(f"    {description}", style="dim"))
        if not compact and index < len(_DESTINATIONS) - 1:
            lines.append(Text())
    return lines


def _center(lines: list[Text], width: int) -> list[Text]:
    cell_lens = [line.cell_len for line in lines]
    block_width = max(cell_lens, default=0)
    indent = max(0, (width - block_width) // 2)
    centered: list[Text] = []
    for line in lines:
        row = Text(" " * indent)
        row.append_text(line)
        centered.append(row)
    return centered


class CalendarMenu(Static, HostedView):
    BINDINGS = [
        Binding("up", "previous_destination", "select destination", show=False),
        Binding("down", "next_destination", "select destination", show=False),
        Binding("enter", "open_destination", "open the selected view", show=False),
        Binding("o", "open_home", "open Google Calendar in the browser", show=False),
    ]
    can_focus = True
    DEFAULT_CSS = """
    CalendarMenu { height: 1fr; width: 100%; content-align: left middle; }
    """

    def __init__(self, panel: CalendarPanel) -> None:
        super().__init__(markup=False)
        self.panel = panel
        self.cursor = 0
        self.elapsed = 0.0
        self.dots_clock = FrameClock(self, BREATH_FPS, self._tick)

    def on_show(self) -> None:
        self.dots_clock.start()

    def on_hide(self) -> None:
        self.dots_clock.stop()

    def _tick(self, elapsed: float) -> None:
        self.elapsed = elapsed
        self.refresh()

    def render(self) -> RenderResult:
        if self.panel.state is PanelState.READY:
            return self.render_content(self.size.width)
        return self.panel.body_text()

    def render_content(self, width: int) -> RenderableType:
        compact = width < _COMPACT_MIN_COLUMNS
        now = self.panel.now()
        next_meeting = self.panel.next_meeting()
        rows: list[Text] = []
        rows.extend(_center([_format_header(now)], width))
        if not compact:
            rows.append(Text())
        rows.extend(_center(_format_icon(now.day), width))
        rows.append(Text())
        rows.extend(_center(_format_countdown(next_meeting, now), width))
        rows.extend(_center([_format_dots(self.elapsed)], width))
        rows.extend(_center(_format_destinations(self.panel, self.cursor, compact), width))
        return Group(*rows)

    def content_lines(self) -> list[str]:
        return plain_lines(self.render_content(self.size.width), self.size.width)

    def refresh_content(self) -> None:
        self.refresh()

    def action_previous_destination(self) -> None:
        self.cursor = step_cursor(self.cursor, -1, len(_DESTINATIONS))
        self.refresh()

    def action_next_destination(self) -> None:
        self.cursor = step_cursor(self.cursor, 1, len(_DESTINATIONS))
        self.refresh()

    def action_open_destination(self) -> None:
        destination = _DESTINATIONS[self.cursor]
        if destination.view not in self.panel.view_classes():
            self.notify("coming in the next milestone")
            return
        self.panel.show_view(destination.view)

    def action_open_home(self) -> None:
        webbrowser.open(CALENDAR_HOME)

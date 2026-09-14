"""One day as a full-day ruler with filled chips and the red now-line, under the week header."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.geometry import Region, Spacing
from textual.widgets import Static

from smorg.integrations.gcal.chips import FALLBACK_COLOR, format_chip, format_markers
from smorg.integrations.gcal.footer import format_footer
from smorg.integrations.gcal.header import format_day_header
from smorg.integrations.gcal.palette import RED
from smorg.integrations.gcal.ruler import Layout, Placed, lay_out
from smorg.integrations.gcal.source import Event
from smorg.integrations.gcal.views import CalendarView
from smorg.shell.cards import SELECTED_MARK
from smorg.shell.cursor import clamp_cursor, step_cursor
from smorg.shell.format import PLAIN_WIDTH, plain_lines
from smorg.shell.panel import GutteredScroll, PanelState, ViewBody
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.gcal.panel import CalendarPanel

RULER_GUTTER = 9
DAYS_PER_WEEK = 7
SCROLL_STEP_ROWS = 4
_BORDERED_FOOTER_MIN_ROWS = 30
_EMPTY_DAY_ANCHOR_SLOT = 32
_SELECTION_SPACING = Spacing(3, 0, 3, 0)
_HINTS = "↑↓ event   ⇧↑↓ scroll   ←→ day   ⏎ details   o open in Calendar   t today   esc menu"


def week_days(focused: date) -> tuple[date, ...]:
    monday = focused - timedelta(days=focused.weekday())
    return tuple(monday + timedelta(days=offset) for offset in range(DAYS_PER_WEEK))


def _chip_text(placed: Placed, row_offset: int) -> str:
    event = placed.event
    start = event.start.strftime("%H:%M")
    if row_offset == 0:
        return f"{start} {event.title}"
    if row_offset == 1:
        return f"{start}–{event.end.strftime('%H:%M')}"
    if row_offset == 2 and event.location:
        return event.location
    return ""


def _format_gutter(label: str, selected: bool) -> Text:
    gutter = Text()
    if selected:
        gutter.append(SELECTED_MARK, style="bold")
    else:
        gutter.append(" ")
    gutter.append(f" {label:>5} ", style="dim")
    gutter.append("│", style="dim")
    return gutter


def _format_now_line(now: datetime, width: int) -> Text:
    line = Text()
    line.append(f"  {now.strftime('%H:%M')} ", style=f"bold {RED}")
    line.append("●", style=f"bold {RED}")
    rule_width = max(0, width - RULER_GUTTER - 1)
    rule = "─" * rule_width
    line.append(rule, style=RED)
    return line


def format_ruler_rows(
    layout: Layout,
    width: int,
    colors: dict[str, str],
    selected_id: str | None,
    now: datetime,
) -> list[Text]:
    """The ruler's rows for one day at `width` columns, chips laid into lanes."""
    content_width = max(1, width - RULER_GUTTER)
    rows: list[Text] = []
    for index, row in enumerate(layout.rows):
        occupants = [
            placed
            for placed in layout.placed
            if placed.first_slot <= row.slot < placed.first_slot + placed.slot_count
        ]
        selected_here = any(placed.event.id == selected_id for placed in occupants)
        if row.hour_rule:
            label = row.time.strftime("%H:%M")
        else:
            label = ""
        line = _format_gutter(label, selected_here)
        if occupants:
            lane_count = max(placed.lane_count for placed in occupants)
            lane_width = content_width // lane_count
            lane_fill_width = lane_width - 1
            lanes = [Text(" " * lane_fill_width)] * lane_count
            for placed in occupants:
                text = _chip_text(placed, row.slot - placed.first_slot)
                if row.slot == placed.first_slot:
                    chip_text = Text(text)
                    chip_text.append(" ")
                    chip_text.append_text(format_markers(placed.event))
                    text = chip_text.plain
                color = colors.get(placed.event.calendar_id, FALLBACK_COLOR)
                past = placed.event.end <= now
                lanes[placed.lane] = format_chip(
                    text, lane_width - 1, color, placed.event.id == selected_id, past
                )
            for lane in lanes:
                line.append_text(lane)
                line.append(" ")
        else:
            line.append(" " * content_width)
        rows.append(line)
        if layout.now_row == index:
            rows.append(_format_now_line(now, width))
    return rows


def _format_all_day(events: tuple[Event, ...], colors: dict[str, str]) -> Text:
    strip = Text(" all day  ", style="dim")
    all_day = [event for event in events if event.all_day]
    if not all_day:
        strip.append("—", style="dim")
        return strip
    for event in all_day:
        color = colors.get(event.calendar_id, FALLBACK_COLOR)
        chip_width = len(event.title) + 2
        strip.append_text(format_chip(event.title, chip_width, color, False, False))
        strip.append("  ")
    return strip


class _Ruler(GutteredScroll):
    can_focus = False

    def __init__(self, draw: Callable[[], RenderableType], id: str) -> None:
        super().__init__(id=id)
        self._draw = draw

    def compose_content(self) -> ComposeResult:
        yield ViewBody(self._draw, id="day-ruler-body")


class CalendarDay(Vertical, HostedView):
    can_focus = True
    BINDINGS = [
        Binding("up", "cursor_up", "select event", show=False),
        Binding("down", "cursor_down", "select event", show=False),
        Binding("shift+up", "scroll_earlier", "scroll an hour earlier", show=False),
        Binding("shift+down", "scroll_later", "scroll an hour later", show=False),
        Binding("left", "previous_day", "previous day", show=False),
        Binding("right", "next_day", "next day", show=False),
        Binding("enter", "open_event", "view event", show=False),
        Binding("o", "open_selected", "open in Google Calendar", show=False),
        Binding("t", "today", "jump to today", show=False),
        Binding("escape", "back_to_menu", "back to menu", show=False),
    ]
    DEFAULT_CSS = """
    CalendarDay { width: 100%; max-width: 120; height: 1fr; }
    CalendarDay > #day-header { dock: top; height: auto; }
    CalendarDay > #day-ruler { height: 1fr; }
    CalendarDay > #day-ruler > #day-ruler-body { height: auto; }
    CalendarDay > #day-footer { dock: bottom; height: auto; }
    """

    def __init__(self, panel: CalendarPanel) -> None:
        super().__init__()
        self.panel = panel
        self.cursor = 0
        self._cursor_day: date | None = None

    def compose(self) -> ComposeResult:
        yield ViewBody(self._render_header, id="day-header")
        yield _Ruler(self._render_ruler, id="day-ruler")
        yield ViewBody(self._render_footer, id="day-footer")

    def _timed(self) -> tuple[Event, ...]:
        focused = self.panel.focused()
        timed = [event for event in self.panel.events_on(focused) if not event.all_day]
        return tuple(timed)

    def _sync_cursor(self) -> None:
        """A fresh day starts the cursor on the next upcoming event, or the last one gone by."""
        focused = self.panel.focused()
        if self._cursor_day == focused:
            return
        self._cursor_day = focused
        now = self.panel.now()
        timed = self._timed()
        self.cursor = 0
        for index, event in enumerate(timed):
            if event.end >= now:
                self.cursor = index
                return
        if timed:
            self.cursor = len(timed) - 1

    def selected_item(self) -> Event | None:
        self._sync_cursor()
        timed = self._timed()
        if not timed:
            return None
        return timed[clamp_cursor(self.cursor, len(timed))]

    def _colors(self) -> dict[str, str]:
        calendars = self.panel.calendars()
        if calendars is None:
            return {}
        return {calendar.id: calendar.color for calendar in calendars.calendars}

    def body_width(self) -> int:
        """The view's own width, or the plain-lines width before it is mounted and measured."""
        if not self.is_mounted:
            return PLAIN_WIDTH
        width = self.size.width
        if width <= 0:
            return PLAIN_WIDTH
        return width

    def _ruler_width(self) -> int:
        if not self.is_mounted:
            return PLAIN_WIDTH - 1
        body = self.query_one("#day-ruler-body", Static)
        width = body.content_size.width
        if width <= 0:
            return PLAIN_WIDTH - 1
        return width

    def _layout_for(self, focused: date) -> Layout:
        events = self.panel.events_on(focused)
        zone = self.panel.zone()
        now = self.panel.now()
        return lay_out(events, focused, zone, now)

    def _bordered(self) -> bool:
        if not self.is_mounted:
            return False
        return self.size.height >= _BORDERED_FOOTER_MIN_ROWS

    def _render_header(self) -> RenderableType:
        if self.panel.state is not PanelState.READY:
            return self.panel.body_text()
        width = self.body_width()
        focused = self.panel.focused()
        days = week_days(focused)
        column_width = max(3, width // DAYS_PER_WEEK)
        initials, numbers = format_day_header(days, self.panel.today(), focused, column_width)
        events = self.panel.events_on(focused)
        colors = self._colors()
        all_day = _format_all_day(events, colors)
        return Group(initials, numbers, all_day)

    def _render_ruler(self) -> RenderableType:
        if self.panel.state is not PanelState.READY:
            return Text()
        width = self._ruler_width()
        focused = self.panel.focused()
        now = self.panel.now()
        colors = self._colors()
        selected = self.selected_item()
        if selected is None:
            selected_id = None
        else:
            selected_id = selected.id
        layout = self._layout_for(focused)
        rows = format_ruler_rows(layout, width, colors, selected_id, now)
        return Group(*rows)

    def _render_footer(self) -> RenderableType:
        if self.panel.state is not PanelState.READY:
            return Text()
        width = self.body_width()
        selected = self.selected_item()
        pieces: list[RenderableType] = []
        if selected is not None:
            calendar = self.panel.calendar_for(selected.calendar_id)
            if calendar is None:
                calendar_name = ""
            else:
                calendar_name = calendar.name
            bordered = self._bordered()
            pieces.append(format_footer(selected, calendar_name, bordered))
        hints = Text(_HINTS, style="dim", justify="center")
        hints.truncate(width, overflow="ellipsis")
        pieces.append(hints)
        return Group(*pieces)

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#day-header", Static).refresh(layout=True)
        self.query_one("#day-ruler-body", Static).refresh()
        self.query_one("#day-footer", Static).refresh(layout=True)

    def content_lines(self) -> list[str]:
        width = self.body_width()
        header = self._render_header()
        ruler_group = self._render_ruler()
        footer = self._render_footer()
        lines = plain_lines(header, width)
        lines.extend(plain_lines(ruler_group, width))
        lines.extend(plain_lines(footer, width))
        return lines

    def _anchor_row(self) -> int:
        focused = self.panel.focused()
        layout = self._layout_for(focused)
        today = self.panel.today()
        if focused == today and layout.now_row is not None:
            return layout.now_row
        if layout.placed:
            first_placed = min(layout.placed, key=lambda placed: placed.first_slot)
            return first_placed.first_slot
        return _EMPTY_DAY_ANCHOR_SLOT

    def _scroll_to_anchor(self) -> None:
        if not self.is_mounted:
            return
        ruler = self.query_one("#day-ruler", _Ruler)
        anchor_row = self._anchor_row()
        viewport_height = ruler.size.height
        third = viewport_height // 3
        offset = anchor_row - third
        target = max(0, offset)
        ruler.scroll_to(y=target, animate=False)

    def _scroll_selection_into_view(self) -> None:
        if not self.is_mounted:
            return
        selected = self.selected_item()
        if selected is None:
            return
        focused = self.panel.focused()
        layout = self._layout_for(focused)
        placed_selected = None
        for placed in layout.placed:
            if placed.event.id == selected.id:
                placed_selected = placed
                break
        if placed_selected is None:
            return
        first_row = placed_selected.first_slot
        if layout.now_row is not None and placed_selected.first_slot > layout.now_row:
            first_row += 1
        region = Region(0, first_row, 1, placed_selected.slot_count)
        ruler = self.query_one("#day-ruler", _Ruler)
        ruler.scroll_to_region(region, spacing=_SELECTION_SPACING, animate=False)

    @property
    def ruler_scroll_y(self) -> float:
        return self.query_one("#day-ruler", VerticalScroll).scroll_y

    def on_show(self) -> None:
        self.call_after_refresh(self._scroll_to_anchor)

    def _move(self, offset: int) -> None:
        timed = self._timed()
        if not timed:
            return
        self.cursor = step_cursor(self.cursor, offset, len(timed))
        self.panel.refresh()
        self.call_after_refresh(self._scroll_selection_into_view)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_scroll_earlier(self) -> None:
        ruler = self.query_one("#day-ruler", _Ruler)
        ruler.scroll_relative(y=-SCROLL_STEP_ROWS, animate=False)

    def action_scroll_later(self) -> None:
        ruler = self.query_one("#day-ruler", _Ruler)
        ruler.scroll_relative(y=SCROLL_STEP_ROWS, animate=False)

    def action_previous_day(self) -> None:
        focused = self.panel.focused()
        previous_day = focused - timedelta(days=1)
        self.panel.set_focused(previous_day)
        self.call_after_refresh(self._scroll_to_anchor)

    def action_next_day(self) -> None:
        focused = self.panel.focused()
        next_day = focused + timedelta(days=1)
        self.panel.set_focused(next_day)
        self.call_after_refresh(self._scroll_to_anchor)

    def action_today(self) -> None:
        today = self.panel.today()
        self.panel.set_focused(today)
        self.call_after_refresh(self._scroll_to_anchor)

    def action_open_event(self) -> None:
        event = self.selected_item()
        if event is None:
            return
        self.panel.open_event(event, CalendarView.DAY)

    def action_open_selected(self) -> None:
        event = self.selected_item()
        if event is None:
            return
        webbrowser.open(event.url)
        self.panel.mark_seen(event)

    def action_back_to_menu(self) -> None:
        self.panel.show_view(CalendarView.MENU)

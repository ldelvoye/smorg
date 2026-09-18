"""One day as a full-day ruler with filled chips and the red now-line, under the week header."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.geometry import Region, Spacing
from textual.widgets import Static

from smorg.integrations.gcal.chips import FALLBACK_COLOR, format_chip, format_markers, pulsed_fill
from smorg.integrations.gcal.footer import format_footer
from smorg.integrations.gcal.header import format_day_header
from smorg.integrations.gcal.palette import BREATH_FPS, RED
from smorg.integrations.gcal.ruler import Layout, Placed, lay_out
from smorg.integrations.gcal.source import Event
from smorg.integrations.gcal.views import CalendarView
from smorg.shell.animation import FrameClock
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


def _format_gutter(label: str, label_style: str) -> Text:
    gutter = Text()
    gutter.append(f"  {label:>5} ", style=label_style)
    gutter.append("│", style="dim")
    return gutter


def overlay_now_rule(row: Text, width: int) -> Text:
    """`row` with the red now rule drawn over it: a dot and a rule across every cell, each chip's
    fill kept underneath."""
    rule = "─" * max(0, width - 1)
    overlaid = Text(f"●{rule}", style=row.style)
    for span in row.spans:
        if isinstance(span.style, str):
            span_style = Style.parse(span.style)
        else:
            span_style = span.style
        if span_style.bgcolor is None:
            continue
        fill_only = Style(bgcolor=span_style.bgcolor)
        overlaid.stylize(fill_only, span.start, span.end)
    overlaid.stylize(f"bold {RED}")
    return overlaid


def format_lane_rows(
    layout: Layout,
    content_width: int,
    colors: dict[str, str],
    selected_id: str | None,
    now: datetime,
    background: str | None = None,
    elapsed: float = 0.0,
) -> list[Text]:
    """One `Text` per slot row: chips laid into lanes, no gutter, no now-line, every row exactly
    `content_width` cells."""
    if background is None:
        row_style = ""
    else:
        row_style = f"on {background}"
    rows: list[Text] = []
    for row in layout.rows:
        line = _format_lane_row(
            layout, row.slot, content_width, colors, selected_id, now, elapsed, row_style
        )
        rows.append(line)
    return rows


def _format_lane_row(
    layout: Layout,
    slot: int,
    content_width: int,
    colors: dict[str, str],
    selected_id: str | None,
    now: datetime,
    elapsed: float,
    row_style: str,
) -> Text:
    occupants = [
        placed
        for placed in layout.placed
        if placed.first_slot <= slot < placed.first_slot + placed.slot_count
    ]
    # A base style sits under the chip fills; stylize() afterwards would paint over them.
    line = Text(style=row_style)
    if not occupants:
        line.append(" " * content_width)
        return line
    lane_count = max(placed.lane_count for placed in occupants)
    lane_width = content_width // lane_count
    lane_fill_width = lane_width - 1
    lanes = [Text(" " * lane_fill_width)] * lane_count
    for placed in occupants:
        text = _chip_text(placed, slot - placed.first_slot)
        if slot == placed.first_slot:
            chip_text = Text(text)
            chip_text.append(" ")
            chip_text.append_text(format_markers(placed.event))
            text = chip_text.plain
        color = colors.get(placed.event.calendar_id, FALLBACK_COLOR)
        past = placed.event.end <= now
        selected = placed.event.id == selected_id
        if selected:
            fill = pulsed_fill(color, elapsed)
        else:
            fill = None
        lanes[placed.lane] = format_chip(text, lane_width - 1, color, selected, past, fill=fill)
    for lane in lanes:
        line.append_text(lane)
        line.append(" ")
    filled_width = lane_count * lane_width
    remainder = content_width - filled_width
    if remainder > 0:
        line.append(" " * remainder)
    return line


def format_ruler_rows(
    layout: Layout,
    width: int,
    colors: dict[str, str],
    selected_id: str | None,
    now: datetime,
    elapsed: float = 0.0,
) -> list[Text]:
    """The ruler's rows for one day at `width` columns, chips laid into lanes."""
    content_width = max(1, width - RULER_GUTTER)
    lane_rows = format_lane_rows(layout, content_width, colors, selected_id, now, elapsed=elapsed)
    rows: list[Text] = []
    for index, row in enumerate(layout.rows):
        if layout.now_row == index:
            label = now.strftime("%H:%M")
            label_style = f"bold {RED}"
            lane_row = overlay_now_rule(lane_rows[index], content_width)
        else:
            if row.hour_rule:
                label = row.time.strftime("%H:%M")
            else:
                label = ""
            label_style = "dim"
            lane_row = lane_rows[index]
        line = _format_gutter(label, label_style)
        line.append_text(lane_row)
        rows.append(line)
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


class RulerScroll(GutteredScroll):
    can_focus = False

    def __init__(self, draw: Callable[[], RenderableType], id: str, body_id: str) -> None:
        super().__init__(id=id)
        self._draw = draw
        self._body_id = body_id

    def compose_content(self) -> ComposeResult:
        yield ViewBody(self._draw, id=self._body_id)


class CalendarDay(Vertical, HostedView):
    can_focus = True
    BINDINGS = [
        Binding("up", "cursor_up", "select event", show=False),
        Binding("down", "cursor_down", "select event", show=False),
        Binding("shift+up", "scroll_earlier", "scroll an hour", show=False),
        Binding("shift+down", "scroll_later", "scroll an hour", show=False),
        Binding("left", "previous_day", "change day", show=False),
        Binding("right", "next_day", "change day", show=False),
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
        self.elapsed = 0.0
        self.pulse_clock = FrameClock(self, BREATH_FPS, self._tick)

    def compose(self) -> ComposeResult:
        yield ViewBody(self._render_header, id="day-header")
        yield RulerScroll(self._render_ruler, id="day-ruler", body_id="day-ruler-body")
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
        rows = format_ruler_rows(layout, width, colors, selected_id, now, elapsed=self.elapsed)
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
        ruler = self.query_one("#day-ruler", RulerScroll)
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
        region = Region(0, placed_selected.first_slot, 1, placed_selected.slot_count)
        ruler = self.query_one("#day-ruler", RulerScroll)
        ruler.scroll_to_region(region, spacing=_SELECTION_SPACING, animate=False)

    @property
    def ruler_scroll_y(self) -> float:
        return self.query_one("#day-ruler", VerticalScroll).scroll_y

    def _tick(self, elapsed: float) -> None:
        self.elapsed = elapsed
        if self.selected_item() is None:
            return
        self.query_one("#day-ruler-body", Static).refresh()

    def on_show(self) -> None:
        self.call_after_refresh(self._scroll_to_anchor)
        self.pulse_clock.start()

    def on_hide(self) -> None:
        self.pulse_clock.stop()

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
        ruler = self.query_one("#day-ruler", RulerScroll)
        ruler.scroll_relative(y=-SCROLL_STEP_ROWS, animate=False)

    def action_scroll_later(self) -> None:
        ruler = self.query_one("#day-ruler", RulerScroll)
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

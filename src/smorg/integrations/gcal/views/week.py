"""Several day columns sharing one scrolling ruler, adapting its column count to the width."""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.geometry import Region, Spacing
from textual.widgets import Static

from smorg.integrations.gcal.chips import FALLBACK_COLOR, format_chip
from smorg.integrations.gcal.footer import format_footer
from smorg.integrations.gcal.header import format_day_header
from smorg.integrations.gcal.palette import BREATH_FPS, RED
from smorg.integrations.gcal.ruler import Layout, lay_out
from smorg.integrations.gcal.source import Event
from smorg.integrations.gcal.views import CalendarView
from smorg.integrations.gcal.views.day import (
    DAYS_PER_WEEK,
    RULER_GUTTER,
    SCROLL_STEP_ROWS,
    RulerScroll,
    _format_gutter,
    format_lane_rows,
    overlay_now_rule,
)
from smorg.shell.animation import FrameClock
from smorg.shell.cursor import clamp_cursor, step_cursor
from smorg.shell.format import PLAIN_WIDTH, plain_lines
from smorg.shell.panel import PanelState, ViewBody
from smorg.shell.terminal_palette import lifted_background, widget_background
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.gcal.panel import CalendarPanel

SLOTS_PER_DAY = 96
_BORDERED_FOOTER_MIN_ROWS = 30
_EMPTY_DAY_ANCHOR_SLOT = 32
_SELECTION_SPACING = Spacing(3, 0, 3, 0)
_HINTS = "↑↓ event   ⇧↑↓ scroll   ←→ day   [ ] week   ⏎ details   o open   t today   esc menu"


def column_count(width: int) -> int:
    """How many day columns fit at `width` columns: 7, 5, 3, or 1."""
    if width >= 140:
        return 7
    if width >= 110:
        return 5
    if width >= 90:
        return 3
    return 1


def visible_days(focused: date, first: date, last: date, count: int) -> tuple[date, ...]:
    """The `count` days to show: a Monday-based week or workweek at 5 or more columns (sliding to
    end on `focused` when it falls past the last shown weekday), else a run centred on `focused`;
    either way slid to stay inside `[first, last]`."""
    if count >= 5:
        if focused.weekday() >= count:
            start = focused - timedelta(days=count - 1)
        else:
            start = focused - timedelta(days=focused.weekday())
    else:
        before = (count - 1) // 2
        start = focused - timedelta(days=before)
    end = start + timedelta(days=count - 1)
    if start < first:
        shift = first - start
        start += shift
        end += shift
    if end > last:
        shift = end - last
        start -= shift
        end -= shift
    return tuple(start + timedelta(days=offset) for offset in range(count))


@dataclass(frozen=True)
class _Column:
    day: date
    width: int
    layout: Layout
    lane_rows: list[Text]


class CalendarWeek(Vertical, HostedView):
    can_focus = True
    BINDINGS = [
        Binding("up", "cursor_up", "select event", show=False),
        Binding("down", "cursor_down", "select event", show=False),
        Binding("shift+up", "scroll_earlier", "scroll an hour", show=False),
        Binding("shift+down", "scroll_later", "scroll an hour", show=False),
        Binding("left", "previous_day", "change day", show=False),
        Binding("right", "next_day", "change day", show=False),
        Binding("left_square_bracket", "previous_week", "change week", show=False),
        Binding("right_square_bracket", "next_week", "change week", show=False),
        Binding("enter", "open_event", "view event", show=False),
        Binding("o", "open_selected", "open in Google Calendar", show=False),
        Binding("t", "today", "jump to today", show=False),
        Binding("escape", "back_to_menu", "back to menu", show=False),
    ]
    DEFAULT_CSS = """
    CalendarWeek { width: 100%; height: 1fr; }
    CalendarWeek > #week-header { dock: top; height: auto; }
    CalendarWeek > #week-ruler { height: 1fr; }
    CalendarWeek > #week-ruler > #week-ruler-body { height: auto; }
    CalendarWeek > #week-footer { dock: bottom; height: auto; }
    """

    def __init__(self, panel: CalendarPanel) -> None:
        super().__init__()
        self.panel = panel
        self.cursor = 0
        self._cursor_day: date | None = None
        self.elapsed = 0.0
        self.pulse_clock = FrameClock(self, BREATH_FPS, self._tick)

    def compose(self) -> ComposeResult:
        yield ViewBody(self._render_header, id="week-header")
        yield RulerScroll(self._render_ruler, id="week-ruler", body_id="week-ruler-body")
        yield ViewBody(self._render_footer, id="week-footer")

    def _timed(self) -> tuple[Event, ...]:
        focused = self.panel.focused()
        timed = [event for event in self.panel.events_on(focused) if not event.all_day]
        return tuple(timed)

    def _sync_cursor(self) -> None:
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
        index = clamp_cursor(self.cursor, len(timed))
        return timed[index]

    def _colors(self) -> dict[str, str]:
        calendars = self.panel.calendars()
        if calendars is None:
            return {}
        return {calendar.id: calendar.color for calendar in calendars.calendars}

    def body_width(self) -> int:
        if not self.is_mounted:
            return PLAIN_WIDTH
        width = self.size.width
        if width <= 0:
            return PLAIN_WIDTH
        return width

    def _ruler_width(self) -> int:
        if not self.is_mounted:
            return PLAIN_WIDTH - 1
        body = self.query_one("#week-ruler-body", Static)
        width = body.content_size.width
        if width <= 0:
            return PLAIN_WIDTH - 1
        return width

    def _shown_days(self, count: int) -> tuple[date, ...]:
        focused = self.panel.focused()
        first, last = self.panel.window()
        return visible_days(focused, first, last, count)

    def _column_widths(self, width: int, count: int) -> list[int]:
        separators = count - 1
        usable = width - RULER_GUTTER - separators
        column_width = max(1, usable // count)
        remainder = usable - column_width * count
        widths = [column_width] * count
        widths[-1] += remainder
        return widths

    def _layout_for(self, day: date) -> Layout:
        events = self.panel.events_on(day)
        zone = self.panel.zone()
        now = self.panel.now()
        return lay_out(events, day, zone, now)

    def _bordered(self) -> bool:
        if not self.is_mounted:
            return False
        return self.size.height >= _BORDERED_FOOTER_MIN_ROWS

    def _hidden_weekend_count(self, shown: tuple[date, ...]) -> int:
        if len(shown) != 5:
            return 0
        week_start = shown[0]
        if week_start.weekday() != 0:
            return 0
        saturday = week_start + timedelta(days=5)
        sunday = week_start + timedelta(days=6)
        saturday_events = self.panel.events_on(saturday)
        sunday_events = self.panel.events_on(sunday)
        hidden_count = len(saturday_events) + len(sunday_events)
        return hidden_count

    def _format_all_day_cell(self, events: list[Event], width: int, colors: dict[str, str]) -> Text:
        if not events:
            return Text(" " * width)
        first_event = events[0]
        extra = len(events) - 1
        if extra > 0:
            suffix = f" +{extra}"
        else:
            suffix = ""
        chip_width = width - len(suffix)
        color = colors.get(first_event.calendar_id, FALLBACK_COLOR)
        chip = format_chip(first_event.title, chip_width, color, False, False)
        cell = Text()
        cell.append_text(chip)
        if suffix:
            cell.append(suffix, style="dim")
        return cell

    def _format_all_day_row(
        self, shown: tuple[date, ...], column_widths: list[int], focused: date, tint: str
    ) -> Text:
        colors = self._colors()
        row = Text(" " * RULER_GUTTER)
        for index, day in enumerate(shown):
            if index:
                row.append(" ")
            events = self.panel.events_on(day)
            all_day = [event for event in events if event.all_day]
            cell = self._format_all_day_cell(all_day, column_widths[index], colors)
            if day == focused:
                cell.style = f"on {tint}"
            row.append_text(cell)
        return row

    def _render_header(self) -> RenderableType:
        if self.panel.state is not PanelState.READY:
            return self.panel.body_text()
        ruler_width = self._ruler_width()
        focused = self.panel.focused()
        today = self.panel.today()
        tint = self._tint()
        count = column_count(ruler_width)
        shown = self._shown_days(count)
        column_widths = self._column_widths(ruler_width, count)
        header_column_width = column_widths[0]
        initials, numbers = format_day_header(shown, today, None, header_column_width + 1)
        prefixed_initials = Text(" " * RULER_GUTTER)
        prefixed_initials.append_text(initials)
        prefixed_numbers = Text(" " * RULER_GUTTER)
        prefixed_numbers.append_text(numbers)
        focused_index = shown.index(focused)
        focused_cell_start = RULER_GUTTER + focused_index * (header_column_width + 1)
        focused_cell_end = focused_cell_start + header_column_width
        prefixed_initials.stylize(f"on {tint}", focused_cell_start, focused_cell_end)
        prefixed_numbers.stylize(f"on {tint}", focused_cell_start, focused_cell_end)
        hidden_count = self._hidden_weekend_count(shown)
        if hidden_count:
            suffix = f" +{hidden_count}"
        else:
            suffix = ""
        if suffix:
            budget = self.body_width() - len(suffix)
            prefixed_numbers.truncate(budget, overflow="ellipsis")
            prefixed_numbers.append(suffix, style="dim")
        all_day_row = self._format_all_day_row(shown, column_widths, focused, tint)
        return Group(prefixed_initials, prefixed_numbers, all_day_row)

    def _tint(self) -> str:
        background = widget_background(self)
        return lifted_background(background)

    def _columns(
        self,
        shown: tuple[date, ...],
        column_widths: list[int],
        selected_id: str | None,
        colors: dict[str, str],
        now: datetime,
        tint: str,
    ) -> list[_Column]:
        focused = self.panel.focused()
        today = self.panel.today()
        columns: list[_Column] = []
        for day, width in zip(shown, column_widths, strict=True):
            layout = self._layout_for(day)
            if day == focused:
                column_selected_id = selected_id
                column_background = tint
                column_elapsed = self.elapsed
            else:
                column_selected_id = None
                column_background = None
                column_elapsed = 0.0
            lane_rows = format_lane_rows(
                layout,
                width,
                colors,
                column_selected_id,
                now,
                background=column_background,
                elapsed=column_elapsed,
            )
            if day == today and layout.now_row is not None:
                now_row = lane_rows[layout.now_row]
                lane_rows[layout.now_row] = overlay_now_rule(now_row, width)
            columns.append(_Column(day=day, width=width, layout=layout, lane_rows=lane_rows))
        return columns

    def _render_ruler(self) -> RenderableType:
        if self.panel.state is not PanelState.READY:
            return Text()
        width = self._ruler_width()
        focused = self.panel.focused()
        today = self.panel.today()
        now = self.panel.now()
        colors = self._colors()
        tint = self._tint()
        selected = self.selected_item()
        if selected is None:
            selected_id = None
        else:
            selected_id = selected.id

        count = column_count(width)
        shown = self._shown_days(count)
        column_widths = self._column_widths(width, count)
        columns = self._columns(shown, column_widths, selected_id, colors, now, tint)

        focused_layout = None
        today_layout = None
        for column in columns:
            if column.day == focused:
                focused_layout = column.layout
            if column.day == today:
                today_layout = column.layout
        assert focused_layout is not None

        rows: list[Text] = []
        for slot in range(SLOTS_PER_DAY):
            row_meta = focused_layout.rows[slot]
            if today_layout is not None and today_layout.now_row == slot:
                label = now.strftime("%H:%M")
                label_style = f"bold {RED}"
            else:
                if row_meta.hour_rule:
                    label = row_meta.time.strftime("%H:%M")
                else:
                    label = ""
                label_style = "dim"
            line = _format_gutter(label, label_style)
            for index, column in enumerate(columns):
                if index:
                    line.append(" ")
                line.append_text(column.lane_rows[slot])
            rows.append(line)
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
        self.query_one("#week-header", Static).refresh(layout=True)
        self.query_one("#week-ruler-body", Static).refresh()
        self.query_one("#week-footer", Static).refresh(layout=True)

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
        ruler = self.query_one("#week-ruler", RulerScroll)
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
        ruler = self.query_one("#week-ruler", RulerScroll)
        ruler.scroll_to_region(region, spacing=_SELECTION_SPACING, animate=False)

    @property
    def ruler_scroll_y(self) -> float:
        return self.query_one("#week-ruler", VerticalScroll).scroll_y

    def _tick(self, elapsed: float) -> None:
        self.elapsed = elapsed
        if self.selected_item() is None:
            return
        self.query_one("#week-ruler-body", Static).refresh()

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
        ruler = self.query_one("#week-ruler", RulerScroll)
        ruler.scroll_relative(y=-SCROLL_STEP_ROWS, animate=False)

    def action_scroll_later(self) -> None:
        ruler = self.query_one("#week-ruler", RulerScroll)
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

    def action_previous_week(self) -> None:
        focused = self.panel.focused()
        target = focused - timedelta(days=DAYS_PER_WEEK)
        self.panel.set_focused(target)
        self.call_after_refresh(self._scroll_to_anchor)

    def action_next_week(self) -> None:
        focused = self.panel.focused()
        target = focused + timedelta(days=DAYS_PER_WEEK)
        self.panel.set_focused(target)
        self.call_after_refresh(self._scroll_to_anchor)

    def action_today(self) -> None:
        today = self.panel.today()
        self.panel.set_focused(today)
        self.call_after_refresh(self._scroll_to_anchor)

    def action_open_event(self) -> None:
        event = self.selected_item()
        if event is None:
            return
        self.panel.open_event(event, CalendarView.WEEK)

    def action_open_selected(self) -> None:
        event = self.selected_item()
        if event is None:
            return
        webbrowser.open(event.url)
        self.panel.mark_seen(event)

    def action_back_to_menu(self) -> None:
        self.panel.show_view(CalendarView.MENU)

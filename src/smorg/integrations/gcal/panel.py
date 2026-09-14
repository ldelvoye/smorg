"""Google Calendar's tab: a host panel that swaps between the landing and the calendar views."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from textual.app import ComposeResult

from smorg.core.contract import Item
from smorg.integrations.gcal.source import (
    Calendar,
    Calendars,
    Event,
    EventKind,
    Response,
    window_for,
)
from smorg.integrations.gcal.views import CalendarView
from smorg.integrations.gcal.views.day import CalendarDay
from smorg.integrations.gcal.views.menu import CalendarMenu
from smorg.shell.animation import FrameClock
from smorg.shell.view_host import HostedView, ViewHostPanel

# One repaint every ten seconds moves the now-line and the countdown without a fetch.
_CLOCK_FPS = 0.1


class CalendarPanel(ViewHostPanel[CalendarView]):
    DEFAULT_CSS = """
    CalendarPanel { align-horizontal: center; }
    """

    def __init__(self) -> None:
        super().__init__(CalendarView.MENU)
        self.now_provider: Callable[[], datetime] | None = None
        self.focused_day: date | None = None
        self.viewed: Event | None = None
        self.return_view: CalendarView = CalendarView.DAY
        self.clock = FrameClock(self, _CLOCK_FPS, self._tick)

    def compose(self) -> ComposeResult:
        yield CalendarMenu(self)
        yield CalendarDay(self)

    def view_classes(self) -> dict[CalendarView, type[HostedView]]:
        return {CalendarView.MENU: CalendarMenu, CalendarView.DAY: CalendarDay}

    def on_mount(self) -> None:
        super().on_mount()
        self.clock.start()

    def _tick(self, elapsed: float) -> None:
        self.refresh()

    def zone(self) -> tzinfo:
        calendars = self.calendars()
        if calendars is None:
            local_zone = datetime.now().astimezone().tzinfo
            if local_zone is not None:
                return local_zone
            return ZoneInfo("UTC")
        try:
            return ZoneInfo(calendars.timezone)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def now(self) -> datetime:
        if self.now_provider is not None:
            return self.now_provider()
        return datetime.now(self.zone())

    def today(self) -> date:
        return self.now().date()

    def focused(self) -> date:
        if self.focused_day is None:
            return self.today()
        return self.focused_day

    def window(self) -> tuple[date, date]:
        start, end = window_for(self.now())
        last = end.date() - timedelta(days=1)
        return start.date(), last

    def set_focused(self, day: date) -> None:
        first, last = self.window()
        if day < first:
            day = first
        if day > last:
            day = last
        self.focused_day = day
        self.refresh()

    def calendars(self) -> Calendars | None:
        for item in self.items:
            if isinstance(item, Calendars):
                return item
        return None

    def calendar_for(self, calendar_id: str) -> Calendar | None:
        calendars = self.calendars()
        if calendars is None:
            return None
        for calendar in calendars.calendars:
            if calendar.id == calendar_id:
                return calendar
        return None

    def events(self) -> tuple[Event, ...]:
        events = [item for item in self.items if isinstance(item, Event)]
        return tuple(events)

    def events_on(self, day: date) -> tuple[Event, ...]:
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=self.zone())
        day_end = day_start + timedelta(days=1)
        on_day = [
            event for event in self.events() if event.start < day_end and event.end > day_start
        ]
        return tuple(on_day)

    def next_meeting(self) -> Event | None:
        now = self.now()
        for event in self.events():
            if event.all_day or event.kind is not EventKind.MEETING:
                continue
            if event.start >= now:
                return event
        return None

    def invites(self) -> tuple[Event, ...]:
        now = self.now()
        pending = [
            event
            for event in self.events()
            if event.my_response is Response.NEEDS_ACTION and event.end >= now
        ]
        return tuple(pending)

    def open_event(self, event: Event, return_view: CalendarView) -> None:
        if CalendarView.EVENT not in self.view_classes():
            self.notify("coming in the next milestone")
            return
        self.viewed = event
        self.return_view = return_view
        self.mark_seen(event)
        self.show_view(CalendarView.EVENT)

    def close_event(self) -> None:
        self.viewed = None
        self.show_view(self.return_view)

    def seen_items(self) -> tuple[Item, ...]:
        return self.events()

    def selected_item(self) -> Item | None:
        if self.active_view is CalendarView.EVENT:
            return self.viewed
        if self.active_view is CalendarView.DAY and self.is_mounted:
            day_view = self.query_one(CalendarDay)
            return day_view.selected_item()
        return None

"""Shared fixtures for Google Calendar panel and view tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from textual.app import App, ComposeResult
from textual.binding import Binding

from smorg.core.contract import Item
from smorg.core.state import SeenState
from smorg.integrations.gcal.panel import CalendarPanel
from smorg.integrations.gcal.source import (
    CALENDARS_ID,
    Attendee,
    Calendar,
    Calendars,
    Event,
    EventKind,
    Response,
)
from smorg.shell.format import symbolize_key_display
from smorg.shell.panel import PanelState

PACIFIC = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 9, 14, 11, 42, tzinfo=PACIFIC)
WORK = Calendar(id="work", name="Work", color="#9fe1e7", primary=True)
TEAM = Calendar(id="team", name="Infra team", color="#b99aff", primary=False)
PERSONAL = Calendar(id="personal", name="Personal", color="#4986e7", primary=False)


def calendars(*entries: Calendar) -> Calendars:
    if not entries:
        entries = (WORK, TEAM, PERSONAL)
    return Calendars(
        id=CALENDARS_ID,
        updated_at=NOW,
        url="https://calendar.google.com",
        timezone="America/Los_Angeles",
        calendars=entries,
    )


def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    day = NOW.date() + timedelta(days=day_offset)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=PACIFIC)


def event(
    identifier: str,
    start: datetime,
    end: datetime,
    title: str | None = None,
    calendar: Calendar = WORK,
    kind: EventKind = EventKind.MEETING,
    my_response: Response = Response.ACCEPTED,
    attendees: tuple[Attendee, ...] = (),
    meet_url: str = "",
    location: str = "",
    all_day: bool = False,
    description: str = "",
) -> Event:
    if title is None:
        title = f"title of {identifier}"
    return Event(
        id=identifier,
        updated_at=NOW,
        url=f"https://www.google.com/calendar/event?eid={identifier}",
        calendar_id=calendar.id,
        title=title,
        start=start,
        end=end,
        all_day=all_day,
        kind=kind,
        my_response=my_response,
        attendees=attendees,
        organizer="Erol Schmidt",
        meet_url=meet_url,
        location=location,
        description=description,
        attachments=(),
        recurring=False,
    )


def attendee(name: str, response: Response, is_self: bool = False) -> Attendee:
    email = name.casefold().replace(" ", ".") + "@example.com"
    return Attendee(name=name, email=email, response=response, organizer=False, is_self=is_self)


def monday_week() -> tuple[Event, ...]:
    """The fixture week the mockups used: Monday 14 with five meetings and an office day."""
    return (
        event(
            "office", at(0, 0), at(1, 0), "Office", kind=EventKind.WORKING_LOCATION, all_day=True
        ),
        event(
            "standup",
            at(0, 9),
            at(0, 9, 30),
            "Infra standup",
            calendar=TEAM,
            meet_url="https://meet.google.com/a",
        ),
        event(
            "erol", at(0, 10, 30), at(0, 11), "Lucas / Erol", meet_url="https://meet.google.com/b"
        ),
        event(
            "design",
            at(0, 12, 30),
            at(0, 13),
            "Design sync: calendar tab",
            my_response=Response.NEEDS_ACTION,
            meet_url="https://meet.google.com/c",
            attendees=(
                attendee("Erol Schmidt", Response.ACCEPTED),
                attendee("Melissa Cao", Response.TENTATIVE),
                attendee("Lucas Delvoye", Response.NEEDS_ACTION, is_self=True),
            ),
        ),
        event(
            "hours",
            at(0, 14),
            at(0, 15),
            "Infra Office Hours",
            calendar=TEAM,
            my_response=Response.NEEDS_ACTION,
            meet_url="https://meet.google.com/d",
        ),
        event(
            "dentist",
            at(0, 16),
            at(0, 16, 45),
            "Dentist",
            calendar=PERSONAL,
            location="Bay Dental, 3rd Ave",
            my_response=Response.NONE,
        ),
        event("standup-tue", at(1, 9), at(1, 9, 30), "Infra standup", calendar=TEAM),
        event("migration", at(1, 11), at(1, 12), "Migration review: pk swap"),
        event("market", at(5, 9), at(5, 10), "Farmers market", calendar=PERSONAL),
    )


def panel_with(*items: Item, seen: SeenState | None = None) -> CalendarPanel:
    panel = CalendarPanel()
    panel.state = PanelState.READY
    panel.items = items
    if seen is None:
        panel.seen = SeenState({})
    else:
        panel.seen = seen
    panel.integration_id = "gcal"
    panel.now_provider = lambda: NOW
    return panel


def week_panel() -> CalendarPanel:
    return panel_with(calendars(), *monday_week())


class PanelHarness(App[None]):
    """The smallest app that can mount a `CalendarPanel` and hand it focus."""

    def __init__(self, panel: CalendarPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel

    def on_mount(self) -> None:
        self._panel.focus()

    def get_key_display(self, binding: Binding) -> str:
        default_display = super().get_key_display(binding)
        return symbolize_key_display(default_display)

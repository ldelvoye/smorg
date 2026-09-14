import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx
import pytest

from smorg.auth.store import Credentials
from smorg.core.contract import AuthExpired
from smorg.integrations.gcal.source import (
    CALENDARS_ID,
    Calendars,
    Event,
    EventKind,
    Response,
    fetch,
)

FIXTURES = Path(__file__).parent / "fixtures"
CALENDAR_LIST = json.loads((FIXTURES / "calendar_list.json").read_text())
TIMEZONE = {"kind": "calendar#setting", "id": "timezone", "value": "America/Los_Angeles"}
NO_EVENTS = {"items": []}

CREDENTIALS = Credentials(
    access_token="gcal-secret-token", refresh_token=None, expires_at=None, scope=""
)


class _Server:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.timezone: tuple[int, object] = (200, TIMEZONE)
        self.calendar_list: tuple[int, object] = (200, CALENDAR_LIST)
        self.events: dict[str, tuple[int, object]] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.raw_path.decode()
        if path.startswith("/calendar/v3/users/me/settings/timezone"):
            status, payload = self.timezone
        elif path.startswith("/calendar/v3/users/me/calendarList"):
            status, payload = self.calendar_list
        elif path.startswith("/calendar/v3/calendars/"):
            encoded = path.removeprefix("/calendar/v3/calendars/").split("/events")[0]
            status, payload = self.events.get(encoded, (200, NO_EVENTS))
        else:
            raise AssertionError(f"unexpected request to {request.url}")
        return httpx.Response(status, json=payload)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))


@pytest.fixture
def server() -> _Server:
    return _Server()


def test_fetch_reads_the_timezone_and_only_the_selected_calendars(server):
    items = fetch(CREDENTIALS, server.client())

    calendars = items[0]
    assert isinstance(calendars, Calendars)
    assert calendars.id == CALENDARS_ID
    assert calendars.timezone == "America/Los_Angeles"
    assert [calendar.name for calendar in calendars.calendars] == [
        "Work",
        "Infra team",
        "US Holidays",
    ]
    assert calendars.calendars[0].primary is True
    assert calendars.calendars[1].color == "#b99aff"


def test_a_calendar_id_with_a_hash_is_encoded_in_the_events_path(server):
    fetch(CREDENTIALS, server.client())

    paths = [request.url.raw_path.decode() for request in server.requests]
    assert any(
        "/calendars/en.usa%23holiday%40group.v.calendar.google.com/events" in p for p in paths
    )


def test_events_are_requested_for_the_two_week_window_as_single_instances(server):
    fetch(CREDENTIALS, server.client())

    event_requests = [r for r in server.requests if "/events" in r.url.path]
    query = parse_qs(event_requests[0].url.query.decode())
    assert query["singleEvents"] == ["true"]
    assert query["orderBy"] == ["startTime"]
    assert query["maxResults"] == ["250"]
    assert "timeMin" in query and "timeMax" in query


def test_a_401_is_auth_expired(server):
    server.timezone = (401, {"error": {"code": 401}})

    with pytest.raises(AuthExpired):
        fetch(CREDENTIALS, server.client())


EVENTS_WORK = json.loads((FIXTURES / "events_work.json").read_text())
WORK = "lucas%40example.com"
PACIFIC = ZoneInfo("America/Los_Angeles")


def _events(server: _Server) -> list[Event]:
    items = fetch(CREDENTIALS, server.client())
    return [item for item in items if isinstance(item, Event)]


def test_events_land_in_the_settings_timezone_with_every_field_mapped(server):
    server.events[WORK] = (200, EVENTS_WORK)

    events = _events(server)
    standup = next(event for event in events if event.id == "standup_20260914")

    assert standup.start == datetime(2026, 9, 14, 9, 0, tzinfo=PACIFIC)
    assert standup.end == datetime(2026, 9, 14, 9, 30, tzinfo=PACIFIC)
    assert standup.all_day is False
    assert standup.kind is EventKind.MEETING
    assert standup.my_response is Response.NEEDS_ACTION
    assert standup.recurring is True
    assert standup.meet_url == "https://meet.google.com/abc-defg-hij"
    assert standup.organizer == "Erol Schmidt"
    assert [attendee.response for attendee in standup.attendees] == [
        Response.ACCEPTED,
        Response.NEEDS_ACTION,
    ]
    assert standup.attendees[1].is_self is True
    assert standup.description == "Agenda\n- mocks\n- landing"
    assert standup.attachments == ("notes.pdf",)
    assert standup.calendar_id == "lucas@example.com"
    assert standup.location == ""


def test_all_day_events_are_midnight_to_exclusive_midnight_and_keep_their_kind(server):
    server.events[WORK] = (200, EVENTS_WORK)

    office = next(event for event in _events(server) if event.id == "office_20260914")

    assert office.all_day is True
    assert office.start == datetime(2026, 9, 14, 0, 0, tzinfo=PACIFIC)
    assert office.end == datetime(2026, 9, 15, 0, 0, tzinfo=PACIFIC)
    assert office.kind is EventKind.WORKING_LOCATION


def test_declined_and_cancelled_instances_are_dropped_and_untitled_events_are_named(server):
    server.events[WORK] = (200, EVENTS_WORK)

    ids = [event.id for event in _events(server)]
    dentist = next(event for event in _events(server) if event.id == "dentist_1")

    assert "declined_1" not in ids
    assert "cancelled_1" not in ids
    assert dentist.title == "(no title)"
    assert dentist.my_response is Response.NONE
    assert dentist.location == "Bay Dental, 3rd Ave"
    assert dentist.organizer == ""


def test_a_404_calendar_is_skipped_while_the_others_load(server):
    server.events[WORK] = (200, EVENTS_WORK)
    server.events["c_team%40group.calendar.google.com"] = (404, {"error": {"code": 404}})

    events = _events(server)

    assert len(events) == 3


def test_events_are_sorted_by_start_across_calendars(server):
    server.events[WORK] = (200, EVENTS_WORK)
    server.events["c_team%40group.calendar.google.com"] = (
        200,
        {
            "items": [
                {
                    "id": "early",
                    "status": "confirmed",
                    "summary": "Early",
                    "htmlLink": "https://www.google.com/calendar/event?eid=early",
                    "updated": "2026-09-01T08:00:00.000Z",
                    "start": {"dateTime": "2026-09-14T07:00:00-07:00"},
                    "end": {"dateTime": "2026-09-14T07:30:00-07:00"},
                    "eventType": "default",
                }
            ]
        },
    )

    assert [event.id for event in _events(server)][:2] == ["office_20260914", "early"]

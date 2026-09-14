"""Fetch the user's selected calendars and two weeks of their events from the Calendar REST API,
mapped to typed items in the user's own timezone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from smorg.auth.store import Credentials, now
from smorg.core.contract import (
    AccessNotAllowed,
    AuthExpired,
    Item,
    Malformed,
    Unavailable,
)
from smorg.core.shape import optional_string, required_string, timestamp
from smorg.core.text import flatten_html, sanitize_block, sanitize_line

API = "https://www.googleapis.com/calendar/v3"
TIMEZONE_ENDPOINT = f"{API}/users/me/settings/timezone"
CALENDAR_LIST_ENDPOINT = f"{API}/users/me/calendarList"
CALENDARS_ID = "calendars"
CALENDAR_HOME = "https://calendar.google.com"
WINDOW_WEEKS = 2
PAGE_SIZE = 250


@dataclass(frozen=True)
class Calendar:
    id: str
    name: str
    color: str
    primary: bool


@dataclass(frozen=True)
class Calendars(Item):
    """The user's selected calendars and the timezone every event was converted into."""

    timezone: str
    calendars: tuple[Calendar, ...]


class EventKind(StrEnum):
    MEETING = "meeting"
    WORKING_LOCATION = "working_location"
    OUT_OF_OFFICE = "out_of_office"
    FOCUS_TIME = "focus_time"


class Response(StrEnum):
    ACCEPTED = "accepted"
    TENTATIVE = "tentative"
    DECLINED = "declined"
    NEEDS_ACTION = "needs_action"
    NONE = "none"


_KINDS = {
    "workingLocation": EventKind.WORKING_LOCATION,
    "outOfOffice": EventKind.OUT_OF_OFFICE,
    "focusTime": EventKind.FOCUS_TIME,
}
_RESPONSES = {
    "accepted": Response.ACCEPTED,
    "tentative": Response.TENTATIVE,
    "declined": Response.DECLINED,
    "needsAction": Response.NEEDS_ACTION,
}
UNTITLED = "(no title)"


@dataclass(frozen=True)
class Attendee:
    name: str
    email: str
    response: Response
    organizer: bool
    is_self: bool


@dataclass(frozen=True)
class Event(Item):
    calendar_id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    kind: EventKind
    my_response: Response
    attendees: tuple[Attendee, ...]
    organizer: str
    meet_url: str
    location: str
    description: str
    attachments: tuple[str, ...]
    recurring: bool


def encoded_calendar_id(calendar_id: str) -> str:
    """A calendar id as a path segment: holiday calendars carry a '#' that a raw path would lose
    as a fragment."""
    return quote(calendar_id, safe="")


def window_for(moment: datetime) -> tuple[datetime, datetime]:
    """Monday 00:00 of moment's week through Monday 00:00 two weeks later, in moment's zone."""
    monday = moment.date() - timedelta(days=moment.weekday())
    start = datetime.combine(monday, datetime.min.time(), tzinfo=moment.tzinfo)
    end = start + timedelta(weeks=WINDOW_WEEKS)
    return start, end


def fetch(credentials: Credentials, http: httpx.Client) -> tuple[Item, ...]:
    zone_name = _fetch_timezone(credentials, http)
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError as error:
        raise Malformed(f"Google named an unknown timezone {zone_name!r}") from error
    calendars = _fetch_calendars(credentials, http)
    calendars_item = Calendars(
        id=CALENDARS_ID,
        updated_at=now(),
        url=CALENDAR_HOME,
        timezone=zone_name,
        calendars=calendars,
    )
    current = now().astimezone(zone)
    window_start, window_end = window_for(current)
    events: list[Event] = []
    for calendar in calendars:
        events.extend(_fetch_events(credentials, http, calendar, zone, window_start, window_end))
    events.sort(key=lambda event: event.start)
    return (calendars_item, *events)


def _get(
    credentials: Credentials, http: httpx.Client, url: str, params: dict[str, Any] | None = None
) -> httpx.Response:
    if params is None:
        request_params = {}
    else:
        request_params = params
    try:
        response = http.get(
            url,
            params=request_params,
            headers={"Authorization": f"Bearer {credentials.access_token}"},
        )
    except httpx.HTTPError as error:
        raise Unavailable("could not reach Google Calendar") from error
    if response.status_code == 401:
        raise AuthExpired("Google rejected the stored token; it may have expired or been revoked")
    if response.status_code == 403:
        raise AccessNotAllowed("Google refused access to the calendar")
    return response


def _require_ok(response: httpx.Response) -> None:
    if response.status_code != 200:
        raise Unavailable(f"Google Calendar returned HTTP {response.status_code}")


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise Malformed("Google Calendar returned a body that is not JSON") from error
    if not isinstance(payload, dict):
        raise Malformed(f"Google Calendar returned {type(payload).__name__}, expected an object")
    return payload


def _items_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list):
        raise Malformed("'items' was not a list")
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise Malformed(f"an item was {type(raw).__name__}, expected an object")
        items.append(raw)
    return items


def _fetch_timezone(credentials: Credentials, http: httpx.Client) -> str:
    response = _get(credentials, http, TIMEZONE_ENDPOINT)
    _require_ok(response)
    payload = _json_object(response)
    return required_string(payload, "value")


def _fetch_calendars(credentials: Credentials, http: httpx.Client) -> tuple[Calendar, ...]:
    response = _get(credentials, http, CALENDAR_LIST_ENDPOINT)
    _require_ok(response)
    payload = _json_object(response)
    calendars: list[Calendar] = []
    for raw in _items_of(payload):
        if raw.get("selected") is not True:
            continue
        summary = required_string(raw, "summary")
        calendars.append(
            Calendar(
                id=required_string(raw, "id"),
                name=sanitize_line(summary),
                color=optional_string(raw, "backgroundColor"),
                primary=raw.get("primary") is True,
            )
        )
    return tuple(calendars)


def _fetch_events(
    credentials: Credentials,
    http: httpx.Client,
    calendar: Calendar,
    zone: ZoneInfo,
    window_start: datetime,
    window_end: datetime,
) -> list[Event]:
    url = f"{API}/calendars/{encoded_calendar_id(calendar.id)}/events"
    params: dict[str, Any] = {
        "timeMin": window_start.isoformat(),
        "timeMax": window_end.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": PAGE_SIZE,
    }
    events: list[Event] = []
    while True:
        response = _get(credentials, http, url, params)
        if response.status_code == 404:
            return []
        _require_ok(response)
        payload = _json_object(response)
        for raw in _items_of(payload):
            event = _event_of(raw, calendar.id, zone)
            if event is not None:
                events.append(event)
        next_page = payload.get("nextPageToken")
        if not isinstance(next_page, str) or not next_page:
            return events
        params = params | {"pageToken": next_page}


def _event_of(raw: dict[str, Any], calendar_id: str, zone: ZoneInfo) -> Event | None:
    if raw.get("status") == "cancelled":
        return None
    attendees = _attendees_of(raw)
    my_response = _my_response_of(attendees)
    if my_response is Response.DECLINED:
        return None
    start, all_day = _moment_of(raw, "start", zone)
    end, _ = _moment_of(raw, "end", zone)
    html_link = required_string(raw, "htmlLink")
    event_type = optional_string(raw, "eventType")
    location = optional_string(raw, "location")
    return Event(
        id=required_string(raw, "id"),
        updated_at=timestamp(raw, "updated"),
        url=_https_url(html_link),
        calendar_id=calendar_id,
        title=_title_of(raw),
        start=start,
        end=end,
        all_day=all_day,
        kind=_KINDS.get(event_type, EventKind.MEETING),
        my_response=my_response,
        attendees=attendees,
        organizer=_organizer_of(raw),
        meet_url=_meet_url_of(raw),
        location=_optional_line(location, limit=200),
        description=_description_of(raw),
        attachments=_attachments_of(raw),
        recurring="recurringEventId" in raw,
    )


def _moment_of(raw: dict[str, Any], key: str, zone: ZoneInfo) -> tuple[datetime, bool]:
    """An event boundary in the user's zone; all-day boundaries are midnight of Google's date."""
    boundary = raw.get(key)
    if not isinstance(boundary, dict):
        raise Malformed(f"'{key}' was {type(boundary).__name__}, expected an object")
    if "dateTime" in boundary:
        stamped = timestamp(boundary, "dateTime")
        return stamped.astimezone(zone), False
    day_text = required_string(boundary, "date")
    try:
        day = datetime.strptime(day_text, "%Y-%m-%d").date()
    except ValueError as error:
        raise Malformed(f"'{key}.date' was not a date: {day_text!r}") from error
    midnight = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    return midnight, True


def _optional_line(value: str, limit: int = 120) -> str:
    """A sanitized line, or empty when the field was empty; sanitize_line alone would name an
    absent field "(unspecified)"."""
    if not value:
        return ""
    return sanitize_line(value, limit=limit)


def _title_of(raw: dict[str, Any]) -> str:
    summary = optional_string(raw, "summary")
    if not summary.strip():
        return UNTITLED
    return sanitize_line(summary)


def _https_url(url: str) -> str:
    scheme = urlsplit(url).scheme
    if scheme != "https":
        raise Malformed("an event link was not https")
    return url


def _meet_url_of(raw: dict[str, Any]) -> str:
    link = optional_string(raw, "hangoutLink")
    if not link:
        return ""
    return _https_url(link)


def _attendees_of(raw: dict[str, Any]) -> tuple[Attendee, ...]:
    raw_attendees = raw.get("attendees", [])
    if not isinstance(raw_attendees, list):
        raise Malformed("'attendees' was not a list")
    attendees: list[Attendee] = []
    for entry in raw_attendees:
        if not isinstance(entry, dict):
            raise Malformed(f"an attendee was {type(entry).__name__}, expected an object")
        raw_email = optional_string(entry, "email")
        email = _optional_line(raw_email)
        name = optional_string(entry, "displayName")
        if not name:
            name = email
        response_status = optional_string(entry, "responseStatus")
        attendees.append(
            Attendee(
                name=_optional_line(name),
                email=email,
                response=_RESPONSES.get(response_status, Response.NONE),
                organizer=entry.get("organizer") is True,
                is_self=entry.get("self") is True,
            )
        )
    return tuple(attendees)


def _my_response_of(attendees: tuple[Attendee, ...]) -> Response:
    for attendee in attendees:
        if attendee.is_self:
            return attendee.response
    return Response.NONE


def _organizer_of(raw: dict[str, Any]) -> str:
    organizer = raw.get("organizer")
    if not isinstance(organizer, dict):
        return ""
    name = optional_string(organizer, "displayName")
    if not name:
        name = optional_string(organizer, "email")
    return _optional_line(name)


def _description_of(raw: dict[str, Any]) -> str:
    text = optional_string(raw, "description")
    if not text:
        return ""
    flattened = flatten_html(text)
    sanitized = sanitize_block(flattened)
    return sanitized.strip()


def _attachments_of(raw: dict[str, Any]) -> tuple[str, ...]:
    raw_attachments = raw.get("attachments", [])
    if not isinstance(raw_attachments, list):
        raise Malformed("'attachments' was not a list")
    titles: list[str] = []
    for entry in raw_attachments:
        if not isinstance(entry, dict):
            raise Malformed(f"an attachment was {type(entry).__name__}, expected an object")
        raw_title = optional_string(entry, "title")
        titles.append(_optional_line(raw_title))
    return tuple(titles)

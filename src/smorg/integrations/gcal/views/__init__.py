"""Google Calendar's views: full-tab looks the host panel swaps between."""

from __future__ import annotations

from enum import StrEnum


class CalendarView(StrEnum):
    MENU = "menu"
    DAY = "day"
    WEEK = "week"
    INVITES = "invites"
    UPCOMING = "upcoming"
    EVENT = "event"

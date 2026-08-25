"""The GraphQL viewer profile: the signed-in user and their contribution calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from smorg.auth.store import Credentials
from smorg.core.contract import Item
from smorg.core.text import sanitize_line

GRAPHQL_URL = "https://api.github.com/graphql"
PROFILE_ID = "github-profile"
# A day the queried range does not cover; rendered blank, unlike a zero-contribution day.
ABSENT_DAY = -1
DAYS_PER_WEEK = 7

# The profile is decoration, not state: a constant stamp keeps it inert to the seen-store.
PROFILE_STAMP = datetime(1970, 1, 1, tzinfo=UTC)

_CONTRIBUTION_LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

_PROFILE_QUERY = """
query {
  viewer {
    login
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { firstDay contributionDays { weekday contributionLevel } }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class ContributionWeek:
    """One week of the contribution calendar: its start date and seven day levels, Sun-Sat."""

    first_day: date
    levels: tuple[int, ...]


@dataclass(frozen=True)
class Profile(Item):
    """The signed-in user and their contribution calendar, or an unavailable placeholder."""

    login: str
    total_contributions: int
    weeks: tuple[ContributionWeek, ...]
    unavailable: bool = False


def _unavailable_profile() -> Profile:
    return Profile(
        id=PROFILE_ID,
        updated_at=PROFILE_STAMP,
        url="https://github.com",
        login="",
        total_contributions=0,
        weeks=(),
        unavailable=True,
    )


def _week_of(raw_week: object) -> ContributionWeek | None:
    """A week's start date and its seven day levels, Sun-Sat; ABSENT_DAY where the range has no
    day. None if misshapen.
    """
    if not isinstance(raw_week, dict):
        return None
    raw_first_day = raw_week.get("firstDay")
    if not isinstance(raw_first_day, str):
        return None
    try:
        first_day = date.fromisoformat(raw_first_day)
    except ValueError:
        return None
    raw_days = raw_week.get("contributionDays")
    if not isinstance(raw_days, list):
        return None
    levels = [ABSENT_DAY] * DAYS_PER_WEEK
    for raw_day in raw_days:
        if not isinstance(raw_day, dict):
            return None
        weekday = raw_day.get("weekday")
        level_name = raw_day.get("contributionLevel")
        if not isinstance(weekday, int) or not 0 <= weekday < DAYS_PER_WEEK:
            return None
        if not isinstance(level_name, str):
            return None
        level = _CONTRIBUTION_LEVELS.get(level_name)
        if level is None:
            return None
        levels[weekday] = level
    return ContributionWeek(first_day=first_day, levels=tuple(levels))


def _profile_of(payload: object) -> Profile:
    """A Profile parsed from the GraphQL response body; unavailable on any shape surprise."""
    if not isinstance(payload, dict):
        return _unavailable_profile()
    data = payload.get("data")
    if not isinstance(data, dict):
        return _unavailable_profile()
    viewer = data.get("viewer")
    if not isinstance(viewer, dict):
        return _unavailable_profile()
    login = viewer.get("login")
    collection = viewer.get("contributionsCollection")
    if not isinstance(login, str) or not isinstance(collection, dict):
        return _unavailable_profile()
    calendar = collection.get("contributionCalendar")
    if not isinstance(calendar, dict):
        return _unavailable_profile()
    total = calendar.get("totalContributions")
    raw_weeks = calendar.get("weeks")
    if not isinstance(total, int) or not isinstance(raw_weeks, list):
        return _unavailable_profile()
    weeks: list[ContributionWeek] = []
    for raw_week in raw_weeks:
        week = _week_of(raw_week)
        if week is None:
            return _unavailable_profile()
        weeks.append(week)
    if not login.strip():
        return _unavailable_profile()
    login_text = sanitize_line(login)
    profile_url = f"https://github.com/{login_text}"
    return Profile(
        id=PROFILE_ID,
        updated_at=PROFILE_STAMP,
        url=profile_url,
        login=login_text,
        total_contributions=total,
        weeks=tuple(weeks),
    )


def query_profile(credentials: Credentials, http: httpx.Client) -> Profile:
    """The viewer's profile over GraphQL; any failure degrades to unavailable, never raises."""
    headers = {"Authorization": f"Bearer {credentials.access_token}"}
    try:
        response = http.post(GRAPHQL_URL, json={"query": _PROFILE_QUERY}, headers=headers)
    except httpx.HTTPError:
        return _unavailable_profile()
    if response.status_code != 200:
        return _unavailable_profile()
    try:
        payload = response.json()
    except ValueError:
        return _unavailable_profile()
    return _profile_of(payload)

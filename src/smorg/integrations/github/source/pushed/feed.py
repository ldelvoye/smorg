"""The events-feed tripwire: a lagged signal that the viewer pushed somewhere the activity
tiers are not watching."""

from __future__ import annotations

from datetime import datetime

import httpx

from smorg.auth.store import Credentials

_EVENTS_URL = "https://api.github.com/users/{login}/events"
_EVENTS_PER_PAGE = 100
_PUSH_EVENT_TYPES = ("PushEvent", "CreateEvent")


def _headers(credentials: Credentials) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credentials.access_token}",
        "Accept": "application/vnd.github+json",
    }


def _stamp_of(raw_event: object) -> tuple[str, datetime] | None:
    if not isinstance(raw_event, dict):
        return None
    event_type = raw_event.get("type")
    if event_type not in _PUSH_EVENT_TYPES:
        return None
    if event_type == "CreateEvent":
        payload = raw_event.get("payload")
        if not isinstance(payload, dict):
            return None
        if payload.get("ref_type") != "branch":
            return None
    raw_created_at = raw_event.get("created_at")
    if not isinstance(raw_created_at, str):
        return None
    try:
        created_at = datetime.fromisoformat(raw_created_at)
    except ValueError:
        return None
    if created_at.tzinfo is None:
        return None
    repo = raw_event.get("repo")
    if not isinstance(repo, dict):
        return None
    name = repo.get("name")
    if not isinstance(name, str) or "/" not in name:
        return None
    return name, created_at


def pushed_repo_stamps(
    credentials: Credentials, http: httpx.Client, login: str
) -> dict[str, datetime]:
    """Repositories the feed's first page says the viewer pushed to, with the newest event
    time per repository; empty on any failure."""
    url = _EVENTS_URL.format(login=login)
    params = {"per_page": _EVENTS_PER_PAGE, "page": 1}
    try:
        response = http.get(url, params=params, headers=_headers(credentials))
    except httpx.HTTPError:
        return {}
    if response.status_code != 200:
        return {}
    try:
        payload = response.json()
    except ValueError:
        return {}
    if not isinstance(payload, list):
        return {}
    stamps: dict[str, datetime] = {}
    for raw_event in payload:
        stamp = _stamp_of(raw_event)
        if stamp is None:
            continue
        name, created_at = stamp
        existing = stamps.get(name)
        if existing is None or created_at > existing:
            stamps[name] = created_at
    return stamps

"""One repository's recent pushes by the viewer, from the repo activity endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from smorg.auth.store import Credentials
from smorg.integrations.github.source.pushed.qualification import WINDOW, PushPair

ACTIVITY_URL = "https://api.github.com/repos/{repo}/activity"
ACTIVITY_PER_PAGE = 100
HOT_TIME_PERIOD = "month"
PROBE_TIME_PERIOD = "quarter"

_KEPT_ACTIVITY_TYPES = ("push", "force_push", "branch_creation")


@dataclass(frozen=True)
class RepoActivity:
    """One repository's activity answer: pushes inside the window, and the newest push seen
    at any age."""

    pairs: list[PushPair]
    newest: datetime | None


def _headers(credentials: Credentials) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credentials.access_token}",
        "Accept": "application/vnd.github+json",
    }


def _pair_of(raw_row: object, repo: str) -> PushPair | None:
    if not isinstance(raw_row, dict):
        return None
    if raw_row.get("activity_type") not in _KEPT_ACTIVITY_TYPES:
        return None
    ref = raw_row.get("ref")
    if not isinstance(ref, str) or not ref.startswith("refs/heads/"):
        return None
    raw_timestamp = raw_row.get("timestamp")
    if not isinstance(raw_timestamp, str):
        return None
    try:
        pushed_at = datetime.fromisoformat(raw_timestamp)
    except ValueError:
        return None
    if pushed_at.tzinfo is None:
        return None
    branch = ref.removeprefix("refs/heads/")
    return PushPair(repository=repo, branch=branch, pushed_at=pushed_at)


def activity_lookup(
    credentials: Credentials,
    http: httpx.Client,
    repo: str,
    login: str,
    now: datetime,
    time_period: str,
) -> RepoActivity | None:
    """The viewer's recent activity on one repository: pushes inside the window, and the
    newest push seen at any age; None on any failure.
    """
    url = ACTIVITY_URL.format(repo=repo)
    params = {"actor": login, "time_period": time_period, "per_page": ACTIVITY_PER_PAGE}
    try:
        response = http.get(url, params=params, headers=_headers(credentials))
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, list):
        return None
    pairs: list[PushPair] = []
    newest: datetime | None = None
    for raw_row in payload:
        pair = _pair_of(raw_row, repo)
        if pair is None:
            continue
        if newest is None or pair.pushed_at > newest:
            newest = pair.pushed_at
        if now - pair.pushed_at <= WINDOW:
            pairs.append(pair)
    return RepoActivity(pairs=pairs, newest=newest)

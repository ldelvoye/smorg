"""The viewer's recently pushed branches that have no pull request yet."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from smorg.auth.store import Credentials
from smorg.integrations.github.source.client import query_graphql
from smorg.integrations.github.source.pushed.qualification import (
    MAX_BRANCHES,
    MAX_PAIRS,
    PUSHED_BRANCHES_ID,
    PUSHED_BRANCHES_STAMP,
    WINDOW,
    PushedBranch,
    PushedBranches,
    PushPair,
    _available_pushed_branches,
    _qualification_query,
    _qualified_branches_of,
    _unavailable_pushed_branches,
)

__all__ = [
    "MAX_BRANCHES",
    "MAX_PAIRS",
    "PUSHED_BRANCHES_ID",
    "PUSHED_BRANCHES_STAMP",
    "WINDOW",
    "PushedBranch",
    "PushedBranches",
    "query_pushed_branches",
]

EVENTS_PER_PAGE = 100
EVENT_PAGE_LIMIT = 3

_USER_URL = "https://api.github.com/user"
_EVENTS_URL = "https://api.github.com/users/{login}/events"


def _rest_headers(credentials: Credentials) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credentials.access_token}",
        "Accept": "application/vnd.github+json",
    }


def _login_of(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    login = payload.get("login")
    if not isinstance(login, str):
        return None
    return login


def _viewer_login(credentials: Credentials, http: httpx.Client) -> str | None:
    """The signed-in viewer's login from GitHub's REST /user endpoint; None on any failure."""
    headers = _rest_headers(credentials)
    try:
        response = http.get(_USER_URL, headers=headers)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return _login_of(payload)


def _event_created_at(raw_event: object) -> datetime | None:
    if not isinstance(raw_event, dict):
        return None
    raw_created_at = raw_event.get("created_at")
    if not isinstance(raw_created_at, str):
        return None
    try:
        created_at = datetime.fromisoformat(raw_created_at)
    except ValueError:
        return None
    # A naive timestamp would make the window arithmetic raise instead of degrade.
    if created_at.tzinfo is None:
        return None
    return created_at


def _events_page(
    credentials: Credentials, http: httpx.Client, login: str, page_number: int
) -> list[object] | None:
    """One page of the viewer's event feed; None on any failure or shape surprise."""
    url = _EVENTS_URL.format(login=login)
    params = {"per_page": EVENTS_PER_PAGE, "page": page_number}
    headers = _rest_headers(credentials)
    try:
        response = http.get(url, params=params, headers=headers)
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
    return payload


def _page_is_exhausted(page: list[object]) -> bool:
    """Whether paging should stop after this page: only a short page proves there is no more.
    The feed is not strictly chronological, so no timestamp cutoff is safe.
    """
    return len(page) < EVENTS_PER_PAGE


def _event_pages(
    credentials: Credentials, http: httpx.Client, login: str
) -> list[list[object]] | None:
    """Up to EVENT_PAGE_LIMIT pages of the viewer's event feed, newest first; None on any
    failure.
    """
    pages: list[list[object]] = []
    for page_number in range(1, EVENT_PAGE_LIMIT + 1):
        page = _events_page(credentials, http, login, page_number)
        if page is None:
            return None
        pages.append(page)
        if _page_is_exhausted(page):
            break
    return pages


def _pushed_branch_of(payload: dict) -> str | None:
    """The branch a PushEvent pushed to, or None for a tag ref or malformed shape."""
    ref = payload.get("ref")
    if not isinstance(ref, str) or not ref.startswith("refs/heads/"):
        return None
    return ref.removeprefix("refs/heads/")


def _created_branch_of(payload: dict) -> str | None:
    """The bare branch name a CreateEvent created, or None for a tag or repository creation."""
    if payload.get("ref_type") != "branch":
        return None
    ref = payload.get("ref")
    if not isinstance(ref, str):
        return None
    return ref


def _pair_of(raw_event: object, now: datetime) -> PushPair | None:
    if not isinstance(raw_event, dict):
        return None
    event_type = raw_event.get("type")
    created_at = _event_created_at(raw_event)
    if created_at is None:
        return None
    if now - created_at > WINDOW:
        return None
    payload = raw_event.get("payload")
    if not isinstance(payload, dict):
        return None
    # A new branch's first push is filed as a CreateEvent; a PushEvent only appears from the
    # second push on.
    if event_type == "PushEvent":
        branch = _pushed_branch_of(payload)
    elif event_type == "CreateEvent":
        branch = _created_branch_of(payload)
    else:
        return None
    if branch is None:
        return None
    repo = raw_event.get("repo")
    if not isinstance(repo, dict):
        return None
    repository = repo.get("name")
    if not isinstance(repository, str) or "/" not in repository:
        return None
    return PushPair(repository=repository, branch=branch, pushed_at=created_at)


def _pushed_pairs_of(pages: list[list[object]], now: datetime) -> list[PushPair]:
    """Distinct (repository, branch) pairs from the event pages, newest push kept per pair,
    newest-first, capped at MAX_PAIRS.
    """
    newest_by_key: dict[tuple[str, str], PushPair] = {}
    for page in pages:
        for raw_event in page:
            pair = _pair_of(raw_event, now)
            if pair is None:
                continue
            key = (pair.repository, pair.branch)
            existing = newest_by_key.get(key)
            if existing is not None and existing.pushed_at >= pair.pushed_at:
                continue
            newest_by_key[key] = pair
    pairs = list(newest_by_key.values())
    newest_first = sorted(pairs, key=lambda pair: pair.pushed_at, reverse=True)
    return newest_first[:MAX_PAIRS]


def _discover_pairs(
    credentials: Credentials, http: httpx.Client, now: datetime
) -> list[PushPair] | None:
    """Up to MAX_PAIRS newest pushed (repository, branch) pairs from the viewer's REST
    event feed; None on any failure.
    """
    login = _viewer_login(credentials, http)
    if login is None:
        return None
    pages = _event_pages(credentials, http, login)
    if pages is None:
        return None
    return _pushed_pairs_of(pages, now)


def query_pushed_branches(credentials: Credentials, http: httpx.Client) -> PushedBranches:
    """The viewer's recently pushed branches with no pull request yet; any failure degrades
    to unavailable, never raises.
    """
    now = datetime.now(UTC)
    pairs = _discover_pairs(credentials, http, now)
    if pairs is None:
        return _unavailable_pushed_branches()
    if not pairs:
        return _available_pushed_branches()
    query = _qualification_query(pairs)
    try:
        response = query_graphql(credentials, http, query)
    except httpx.HTTPError:
        return _unavailable_pushed_branches()
    if response.status_code != 200:
        return _unavailable_pushed_branches()
    try:
        payload = response.json()
    except ValueError:
        return _unavailable_pushed_branches()
    return _qualified_branches_of(payload, pairs)

"""The viewer's recently pushed branches that have no pull request yet."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx

from smorg.auth.store import Credentials
from smorg.core.contract import Item
from smorg.core.text import sanitize_line
from smorg.integrations.github.source.client import query_graphql

PUSHED_BRANCHES_ID = "github-pushed-branches"

# The container is decoration, not state: a constant stamp keeps it inert to the seen-store.
PUSHED_BRANCHES_STAMP = datetime(1970, 1, 1, tzinfo=UTC)

MAX_BRANCHES = 20
# Wider than MAX_BRANCHES: qualification discards PR-associated pairs, so a tight discovery cap
# would let busy pull request branches crowd out fresh ones.
MAX_PAIRS = 50
WINDOW = timedelta(days=7)
EVENTS_PER_PAGE = 100
EVENT_PAGE_LIMIT = 3

_USER_URL = "https://api.github.com/user"
_EVENTS_URL = "https://api.github.com/users/{login}/events"


@dataclass(frozen=True)
class PushedBranch(Item):
    repository: str
    branch: str
    headline: str
    compare_url: str


@dataclass(frozen=True)
class PushedBranches(Item):
    """Every qualifying pushed branch, or an unavailable placeholder."""

    branches: tuple[PushedBranch, ...]
    unavailable: bool = False


@dataclass(frozen=True)
class _PushPair:
    """A (repository, branch) discovered from the event feed, and when it was last pushed."""

    repository: str
    branch: str
    pushed_at: datetime


def _unavailable_pushed_branches() -> PushedBranches:
    return PushedBranches(
        id=PUSHED_BRANCHES_ID,
        updated_at=PUSHED_BRANCHES_STAMP,
        url="https://github.com",
        branches=(),
        unavailable=True,
    )


def _available_pushed_branches(branches: tuple[PushedBranch, ...] = ()) -> PushedBranches:
    return PushedBranches(
        id=PUSHED_BRANCHES_ID,
        updated_at=PUSHED_BRANCHES_STAMP,
        url="https://github.com",
        branches=branches,
    )


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


def _pair_of(raw_event: object, now: datetime) -> _PushPair | None:
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
    return _PushPair(repository=repository, branch=branch, pushed_at=created_at)


def _pushed_pairs_of(pages: list[list[object]], now: datetime) -> list[_PushPair]:
    """Distinct (repository, branch) pairs from the event pages, newest push kept per pair,
    newest-first, capped at MAX_PAIRS.
    """
    newest_by_key: dict[tuple[str, str], _PushPair] = {}
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
) -> list[_PushPair] | None:
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


def _alias(index: int) -> str:
    return f"b{index}"


def _qualification_alias(index: int, pair: _PushPair) -> str:
    """One aliased repository/ref lookup for a discovered pair."""
    owner, name = pair.repository.split("/", 1)
    qualified_name = f"refs/heads/{pair.branch}"
    # json.dumps escapes quotes and backslashes, so a hostile branch name cannot break out of
    # the query.
    return (
        f"{_alias(index)}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{\n"
        f"    defaultBranchRef {{ name }}\n"
        f"    ref(qualifiedName: {json.dumps(qualified_name)}) {{\n"
        f"      associatedPullRequests(first: 1) {{ totalCount }}\n"
        f"      target {{ ... on Commit {{ messageHeadline parents {{ totalCount }} }} }}\n"
        f"    }}\n"
        f"  }}"
    )


def _qualification_query(pairs: list[_PushPair]) -> str:
    """The one-POST GraphQL query qualifying every discovered pair, one aliased lookup each."""
    aliases: list[str] = []
    for index, pair in enumerate(pairs):
        aliases.append(_qualification_alias(index, pair))
    body = "\n  ".join(aliases)
    return f"query {{\n  {body}\n}}"


def _default_branch_name_of(raw_default_branch_ref: object) -> str | None:
    if not isinstance(raw_default_branch_ref, dict):
        return None
    name = raw_default_branch_ref.get("name")
    if not isinstance(name, str):
        return None
    return name


def _associated_pull_request_count_of(raw_ref: dict) -> int | None:
    associated = raw_ref.get("associatedPullRequests")
    if not isinstance(associated, dict):
        return None
    count = associated.get("totalCount")
    if not isinstance(count, int):
        return None
    return count


def _commit_of(raw_target: object) -> tuple[str, int] | None:
    """The tip commit's headline and parent count; None when the target is not a Commit or is
    misshapen.
    """
    if not isinstance(raw_target, dict):
        return None
    headline = raw_target.get("messageHeadline")
    if not isinstance(headline, str):
        return None
    raw_parents = raw_target.get("parents")
    if not isinstance(raw_parents, dict):
        return None
    parent_count = raw_parents.get("totalCount")
    if not isinstance(parent_count, int):
        return None
    return headline, parent_count


def _qualified_branch_of(raw_alias: object, pair: _PushPair) -> PushedBranch | None:
    if not isinstance(raw_alias, dict):
        return None
    raw_ref = raw_alias.get("ref")
    if not isinstance(raw_ref, dict):
        return None
    default_branch_name = _default_branch_name_of(raw_alias.get("defaultBranchRef"))
    if default_branch_name is not None and pair.branch == default_branch_name:
        return None
    associated_count = _associated_pull_request_count_of(raw_ref)
    if associated_count != 0:
        return None
    commit = _commit_of(raw_ref.get("target"))
    if commit is None:
        return None
    headline, parent_count = commit
    # 2+ parents means the tip is a merge commit, not a fresh push.
    if parent_count >= 2:
        return None
    repository_text = sanitize_line(pair.repository)
    branch_text = sanitize_line(pair.branch)
    headline_text = sanitize_line(headline)
    quoted_branch = quote(branch_text, safe="/")
    return PushedBranch(
        id=f"{repository_text}:{branch_text}",
        updated_at=pair.pushed_at,
        url=f"https://github.com/{repository_text}/tree/{quoted_branch}",
        repository=repository_text,
        branch=branch_text,
        headline=headline_text,
        compare_url=f"https://github.com/{repository_text}/pull/new/{quoted_branch}",
    )


def _qualified_branches_of(payload: object, pairs: list[_PushPair]) -> PushedBranches:
    """Every pair that survives qualification, newest-first and capped at MAX_BRANCHES;
    unavailable on a shape surprise.
    """
    if not isinstance(payload, dict):
        return _unavailable_pushed_branches()
    data = payload.get("data")
    if not isinstance(data, dict):
        return _unavailable_pushed_branches()
    branches: list[PushedBranch] = []
    for index, pair in enumerate(pairs):
        raw_alias = data.get(_alias(index))
        branch = _qualified_branch_of(raw_alias, pair)
        if branch is not None:
            branches.append(branch)
    newest_first = sorted(branches, key=lambda branch: branch.updated_at, reverse=True)
    return _available_pushed_branches(tuple(newest_first[:MAX_BRANCHES]))


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

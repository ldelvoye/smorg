"""The viewer's recently pushed branches that have no open or merged pull request yet."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from smorg.auth.store import Credentials
from smorg.integrations.github.source.client import query_graphql
from smorg.integrations.github.source.pushed.activity import HOT_TIME_PERIOD, activity_pairs
from smorg.integrations.github.source.pushed.discovery import discover_repos
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
    "PushPair",
    "query_pushed_branches",
]


def _newest_pairs(pairs: list[PushPair]) -> list[PushPair]:
    """Distinct (repository, branch) pairs, newest push kept per pair, newest-first, capped
    at MAX_PAIRS.
    """
    newest_by_key: dict[tuple[str, str], PushPair] = {}
    for pair in pairs:
        key = (pair.repository, pair.branch)
        existing = newest_by_key.get(key)
        if existing is not None and existing.pushed_at >= pair.pushed_at:
            continue
        newest_by_key[key] = pair
    deduped = list(newest_by_key.values())
    newest_first = sorted(deduped, key=lambda pair: pair.pushed_at, reverse=True)
    return newest_first[:MAX_PAIRS]


def query_pushed_branches(credentials: Credentials, http: httpx.Client) -> PushedBranches:
    """The viewer's recently pushed branches with no open or merged pull request yet; any
    failure degrades to unavailable, never raises. A single repository's failure only loses
    that repository.
    """
    now = datetime.now(UTC)
    discovered = discover_repos(credentials, http, now)
    if discovered is None:
        return _unavailable_pushed_branches()
    login, candidates = discovered
    found: list[PushPair] = []
    for candidate in candidates:
        repo_pairs = activity_pairs(credentials, http, candidate.name, login, now, HOT_TIME_PERIOD)
        if repo_pairs is None:
            continue
        found.extend(repo_pairs)
    pairs = _newest_pairs(found)
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

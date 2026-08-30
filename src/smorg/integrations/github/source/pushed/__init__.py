"""The viewer's recently pushed branches that have no open or merged pull request yet."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from smorg.auth.store import Credentials
from smorg.integrations.github.source.client import query_graphql
from smorg.integrations.github.source.pushed.activity import activity_pairs
from smorg.integrations.github.source.pushed.discovery import discover_repos
from smorg.integrations.github.source.pushed.feed import pushed_repo_stamps
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
from smorg.integrations.github.source.pushed.state import ActivityCache
from smorg.integrations.github.source.pushed.tiers import (
    RETIREMENT,
    RepoRecord,
    observed,
    plan_refresh,
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


def query_pushed_branches(
    credentials: Credentials, http: httpx.Client, cache: ActivityCache | None = None
) -> PushedBranches:
    """The viewer's recently pushed branches with no open or merged pull request yet; any
    failure degrades to unavailable, never raises. A single repository's failure only loses
    that repository.
    """
    now = datetime.now(UTC)
    if cache is None:
        cache = ActivityCache.load()
    discovered = discover_repos(credentials, http, now)
    if discovered is None:
        return _unavailable_pushed_branches()
    login, candidates = discovered
    names = [candidate.name for candidate in candidates]
    tripped = pushed_repo_stamps(credentials, http, login)
    for name, stamp in tripped.items():
        record = cache.records.get(name)
        # Only unknown and retired repos get promoted: the feed lags hours behind the
        # activity endpoint, so a hot or cold repo's own calls are fresher.
        if record is not None and record.last_probed is not None:
            if record.last_activity is not None and now - record.last_activity <= RETIREMENT:
                continue
        cache.records[name] = RepoRecord(last_activity=stamp, last_probed=stamp)
        if name not in names:
            names.append(name)
    for name in cache.records:
        if name not in names:
            names.append(name)
    plan = plan_refresh(names, cache.records, cache.cursor, now)
    found: list[PushPair] = []
    failures = 0
    for name, time_period in plan.calls:
        repo_pairs = activity_pairs(credentials, http, name, login, now, time_period)
        if repo_pairs is None:
            failures += 1
            continue
        if repo_pairs:
            newest_pair = max(pair.pushed_at for pair in repo_pairs)
        else:
            newest_pair = None
        cache.records[name] = observed(cache.records.get(name), newest_pair, now)
        found.extend(repo_pairs)
    cache.cursor = plan.cursor
    cache.save()
    if plan.calls and failures == len(plan.calls):
        return _unavailable_pushed_branches()
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

"""The viewer's recently pushed branches that have no open or merged pull request yet."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import httpx

from smorg.auth.store import Credentials
from smorg.core.config import ConfigError
from smorg.integrations.github.source.client import query_graphql
from smorg.integrations.github.source.pushed.activity import activity_lookup
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
    RepoRecord,
    observed,
    plan_refresh,
    should_promote,
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
        if not should_promote(record, now):
            continue
        cache.records[name] = RepoRecord(last_activity=stamp, last_probed=now)
    for name in cache.records:
        if name not in names:
            names.append(name)
    plan = plan_refresh(names, cache.records, cache.cursor, now)
    fine_grained_token = credentials.access_token.startswith("github_pat_")
    found: list[PushPair] = []
    failed_repos: list[str] = []
    for name, time_period in plan.calls:
        lookup = activity_lookup(credentials, http, name, login, now, time_period)
        if lookup is None:
            failed_repos.append(name)
            continue
        cache.records[name] = observed(cache.records.get(name), lookup.newest, now)
        found.extend(lookup.pairs)
    cache.cursor = plan.cursor
    try:
        cache.save()
    except (ConfigError, OSError):
        pass
    if plan.calls and len(failed_repos) == len(plan.calls):
        return _unavailable_pushed_branches()
    pairs = _newest_pairs(found)
    if not pairs:
        return _available_pushed_branches(
            failed_repos=tuple(failed_repos), fine_grained_token=fine_grained_token
        )
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
    result = _qualified_branches_of(payload, pairs)
    if result.unavailable:
        return result
    return replace(result, failed_repos=tuple(failed_repos), fine_grained_token=fine_grained_token)

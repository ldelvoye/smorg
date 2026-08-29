"""Qualification of discovered branch pushes over one GraphQL POST."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from smorg.core.contract import Item
from smorg.core.text import sanitize_line

PUSHED_BRANCHES_ID = "github-pushed-branches"

# The container is decoration, not state: a constant stamp keeps it inert to the seen-store.
PUSHED_BRANCHES_STAMP = datetime(1970, 1, 1, tzinfo=UTC)

MAX_BRANCHES = 20
# Wider than MAX_BRANCHES: qualification discards PR-associated pairs, so a tight discovery cap
# would let busy pull request branches crowd out fresh ones.
MAX_PAIRS = 50
WINDOW = timedelta(days=30)


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
class PushPair:
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


def _alias(index: int) -> str:
    return f"b{index}"


def _qualification_alias(index: int, pair: PushPair) -> str:
    """One aliased repository/ref lookup for a discovered pair."""
    owner, name = pair.repository.split("/", 1)
    qualified_name = f"refs/heads/{pair.branch}"
    # json.dumps escapes quotes and backslashes, so a hostile branch name cannot break out of
    # the query.
    return (
        f"{_alias(index)}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{\n"
        f"    defaultBranchRef {{ name }}\n"
        f"    ref(qualifiedName: {json.dumps(qualified_name)}) {{\n"
        f"      associatedPullRequests(states: [OPEN, MERGED], first: 1) {{ totalCount }}\n"
        f"      target {{ ... on Commit {{ messageHeadline parents {{ totalCount }} }} }}\n"
        f"    }}\n"
        f"  }}"
    )


def _qualification_query(pairs: list[PushPair]) -> str:
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


def _qualified_branch_of(raw_alias: object, pair: PushPair) -> PushedBranch | None:
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


def _qualified_branches_of(payload: object, pairs: list[PushPair]) -> PushedBranches:
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

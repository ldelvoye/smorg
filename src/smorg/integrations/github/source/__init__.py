"""Fetch pull requests from GitHub through PyGithub and map them to typed items."""

from __future__ import annotations

from smorg.integrations.github.source.detail import (
    ABSENT_COUNT,
    UNAVAILABLE_CHECKS,
    CheckSummary,
    Comment,
    LineCounts,
    PullRequestDetail,
    Reviewer,
    ReviewerState,
    fetch_detail,
)
from smorg.integrations.github.source.diff import (
    DiffRequest,
    FileDiff,
    PullRequestDiff,
    diff_request_of,
    fetch_diff,
)
from smorg.integrations.github.source.fetch import FETCH_PHASES, fetch, fetch_with_progress
from smorg.integrations.github.source.profile import (
    ABSENT_DAY,
    DAYS_PER_WEEK,
    PROFILE_ID,
    ContributionWeek,
    Profile,
)
from smorg.integrations.github.source.pushed import (
    PUSHED_BRANCHES_ID,
    PushedBranch,
    PushedBranches,
    query_pushed_branches,
)
from smorg.integrations.github.source.search import Category, PullRequest

__all__ = [
    "ABSENT_COUNT",
    "ABSENT_DAY",
    "DAYS_PER_WEEK",
    "FETCH_PHASES",
    "PROFILE_ID",
    "PUSHED_BRANCHES_ID",
    "UNAVAILABLE_CHECKS",
    "Category",
    "CheckSummary",
    "Comment",
    "ContributionWeek",
    "DiffRequest",
    "FileDiff",
    "LineCounts",
    "Profile",
    "PullRequest",
    "PullRequestDetail",
    "PullRequestDiff",
    "PushedBranch",
    "PushedBranches",
    "Reviewer",
    "ReviewerState",
    "diff_request_of",
    "fetch",
    "fetch_detail",
    "fetch_diff",
    "fetch_with_progress",
    "query_pushed_branches",
]

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
from smorg.integrations.github.source.fetch import fetch
from smorg.integrations.github.source.profile import (
    ABSENT_DAY,
    DAYS_PER_WEEK,
    PROFILE_ID,
    ContributionWeek,
    Profile,
)
from smorg.integrations.github.source.search import Category, PullRequest

__all__ = [
    "ABSENT_COUNT",
    "ABSENT_DAY",
    "DAYS_PER_WEEK",
    "PROFILE_ID",
    "UNAVAILABLE_CHECKS",
    "Category",
    "CheckSummary",
    "Comment",
    "ContributionWeek",
    "LineCounts",
    "Profile",
    "PullRequest",
    "PullRequestDetail",
    "Reviewer",
    "ReviewerState",
    "fetch",
    "fetch_detail",
]

"""The five-request detail: body, branches, reviewers, comments, line counts, and checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import httpx
import requests
from github import BadAttributeException, GithubException
from github.IssueComment import IssueComment
from github.PullRequest import PullRequest as GithubPullRequest
from github.PullRequestReview import PullRequestReview
from github.Repository import Repository

from smorg.auth.store import Credentials
from smorg.core.contract import Item, Malformed, Newest
from smorg.core.text import sanitize_block, sanitize_line, truncate
from smorg.integrations.github.source.client import connect, first, github_errors
from smorg.integrations.github.source.search import PullRequest

REVIEWS_FETCH_LIMIT = 25
BODY_LIMIT = 50_000
COMMENT_LIMIT = 5
COMMENTS_FETCH_LIMIT = 25
COMMENT_BODY_LIMIT = 5_000
FAILED_NAMES_LIMIT = 10
CHECK_RUNS_FETCH_LIMIT = 100
# A count the payload did not carry; rendered as absent, unlike a real zero.
ABSENT_COUNT = -1

_PASSED_CONCLUSIONS = {"success", "neutral", "skipped"}
_FAILED_CONCLUSIONS = {"failure", "timed_out", "cancelled", "action_required"}


class ReviewerState(StrEnum):
    """A reviewer's standing on the pull request, GitHub-sidebar style."""

    REQUESTED = "requested"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes requested"
    LEFT_COMMENTS = "left comments"
    DISMISSED = "dismissed"


@dataclass(frozen=True)
class Reviewer:
    name: str
    state: ReviewerState
    # None for a requested reviewer who has not reviewed yet.
    submitted_at: datetime | None


_DECIDED_STATES = {
    "APPROVED": ReviewerState.APPROVED,
    "CHANGES_REQUESTED": ReviewerState.CHANGES_REQUESTED,
    "DISMISSED": ReviewerState.DISMISSED,
}

# Display order: what still blocks the pull request first.
_STATE_ORDER = (
    ReviewerState.REQUESTED,
    ReviewerState.CHANGES_REQUESTED,
    ReviewerState.APPROVED,
    ReviewerState.LEFT_COMMENTS,
    ReviewerState.DISMISSED,
)


@dataclass(frozen=True)
class Comment:
    author: str
    submitted_at: datetime | None
    body: str


@dataclass(frozen=True)
class LineCounts:
    additions: int = ABSENT_COUNT
    deletions: int = ABSENT_COUNT
    changed_files: int = ABSENT_COUNT


@dataclass(frozen=True)
class CheckSummary:
    """Pass/fail/running totals for a head commit, with the failing runs' names."""

    passed: int
    failed: int
    running: int
    failed_names: tuple[str, ...]
    # Failing runs beyond FAILED_NAMES_LIMIT, counted rather than named.
    hidden_failed: int = 0
    # The fetch hit CHECK_RUNS_FETCH_LIMIT, so every count is a lower bound.
    truncated: bool = False
    available: bool = True


UNAVAILABLE_CHECKS = CheckSummary(passed=0, failed=0, running=0, failed_names=(), available=False)


@dataclass(frozen=True)
class PullRequestDetail:
    body: str
    base: str
    head: str
    reviewers: tuple[Reviewer, ...]
    comments: Newest[Comment]
    counts: LineCounts
    checks: CheckSummary


def fetch_detail(credentials: Credentials, http: httpx.Client, item: Item) -> PullRequestDetail:
    """The selected pull request's expanded view: description, branches, line counts, checks,
    reviews, and the newest comments.
    """
    if not isinstance(item, PullRequest):
        raise Malformed(f"expected a pull request, got {type(item).__name__}")
    with connect(credentials, lazy=True) as client, github_errors():
        repository = client.get_repo(item.repository)
        pr = repository.get_pull(item.number)
        if pr.base:
            base_ref = pr.base.ref
        else:
            base_ref = ""
        if pr.head:
            head_ref = pr.head.ref
        else:
            head_ref = ""
        return PullRequestDetail(
            body=_body_of(pr),
            base=sanitize_line(base_ref),
            head=sanitize_line(head_ref),
            reviewers=_reviewers_of(pr, item.author),
            comments=_comments_of(pr),
            counts=_counts_of(pr),
            checks=_checks_of(repository, pr),
        )


def _body_of(pr: GithubPullRequest) -> str:
    """The description, sanitized and capped, or "" if there is none."""
    raw = pr.body
    if not isinstance(raw, str):
        return ""
    return truncate(sanitize_block(raw, limit=None), BODY_LIMIT)


def _reviewers_of(pr: GithubPullRequest, author: str) -> tuple[Reviewer, ...]:
    """One entry per person or team with standing in the review, requested first."""
    raw_events = first(pr.get_reviews(), REVIEWS_FETCH_LIMIT)
    commented = _commented_of(raw_events, author)
    decided = _decided_of(raw_events)
    requested = _requested_of(pr)
    by_name: dict[str, Reviewer] = {}
    # Overlay order is precedence: a request beats a past decision, which beats mere comments.
    for name, reviewer in commented.items():
        by_name[name] = reviewer
    for name, reviewer in decided.items():
        by_name[name] = reviewer
    for name in requested:
        by_name[name] = Reviewer(name=name, state=ReviewerState.REQUESTED, submitted_at=None)
    ordered: list[Reviewer] = []
    for state in _STATE_ORDER:
        for reviewer in by_name.values():
            if reviewer.state is state:
                ordered.append(reviewer)
    return tuple(ordered)


def _commented_of(raw_events: list[PullRequestReview], author: str) -> dict[str, Reviewer]:
    """Each commenter's latest comment-only review, keyed by name.

    The author's COMMENTED wrappers (GitHub's empty artifacts around single inline
    comments) are not reviewer states and are dropped.
    """
    commented: dict[str, Reviewer] = {}
    for raw in raw_events:
        name = _event_author_of(raw)
        if name is None or raw.state != "COMMENTED" or name == author:
            continue
        reviewer = Reviewer(
            name=name, state=ReviewerState.LEFT_COMMENTS, submitted_at=_event_moment_of(raw)
        )
        commented[name] = reviewer
    return commented


def _decided_of(raw_events: list[PullRequestReview]) -> dict[str, Reviewer]:
    """Each reviewer's latest approval, change request, or dismissal, keyed by name."""
    decided: dict[str, Reviewer] = {}
    for raw in raw_events:
        name = _event_author_of(raw)
        state = _DECIDED_STATES.get(raw.state)
        if name is None or state is None:
            continue
        decided[name] = Reviewer(name=name, state=state, submitted_at=_event_moment_of(raw))
    return decided


def _event_author_of(raw: PullRequestReview) -> str | None:
    """The sanitized login behind a review event, or None for a deleted account."""
    user = raw.user
    if user is None or not isinstance(user.login, str) or not user.login:
        return None
    return sanitize_line(user.login)


def _event_moment_of(raw: PullRequestReview) -> datetime | None:
    """When the review was submitted, or None when GitHub omitted it."""
    if isinstance(raw.submitted_at, datetime):
        return raw.submitted_at
    return None


def _requested_of(pr: GithubPullRequest) -> list[str]:
    """Requested reviewers as display names: user logins, then teams as #slug."""
    try:
        users = pr.requested_reviewers
        teams = pr.requested_teams
    except BadAttributeException:
        return []
    names: list[str] = []
    for user in users:
        if isinstance(user.login, str) and user.login:
            names.append(sanitize_line(user.login))
    for team in teams:
        if isinstance(team.slug, str) and team.slug:
            names.append(f"#{sanitize_line(team.slug)}")
    return names


def _comments_of(pr: GithubPullRequest) -> Newest[Comment]:
    raw_comments = first(pr.get_issue_comments(), COMMENTS_FETCH_LIMIT)
    all_comments = [_comment_of(raw) for raw in raw_comments]
    return Newest(
        items=tuple(all_comments[-COMMENT_LIMIT:]),
        hidden=max(0, len(all_comments) - COMMENT_LIMIT),
        hidden_is_lower_bound=len(raw_comments) >= COMMENTS_FETCH_LIMIT,
    )


def _comment_of(raw: IssueComment) -> Comment:
    """A typed Comment; anything GitHub omitted degrades to "" or None."""
    author = raw.user
    if author is None or not isinstance(author.login, str):
        name = ""
    else:
        name = sanitize_line(author.login)
    if isinstance(raw.body, str):
        body = truncate(sanitize_block(raw.body, limit=None), COMMENT_BODY_LIMIT)
    else:
        body = ""
    if isinstance(raw.created_at, datetime):
        submitted_at = raw.created_at
    else:
        submitted_at = None
    return Comment(author=name, submitted_at=submitted_at, body=body)


def _counts_of(pr: GithubPullRequest) -> LineCounts:
    """The line-change counts; all absent on a misshapen payload."""
    try:
        additions = pr.additions
        deletions = pr.deletions
        changed_files = pr.changed_files
    except BadAttributeException:
        return LineCounts()
    return LineCounts(
        additions=_count_of(additions),
        deletions=_count_of(deletions),
        changed_files=_count_of(changed_files),
    )


def _count_of(value: object) -> int:
    """A non-negative count from the payload, or ABSENT_COUNT when missing or misshapen."""
    if not isinstance(value, int) or value < 0:
        return ABSENT_COUNT
    return value


def _checks_of(repository: Repository, pr: GithubPullRequest) -> CheckSummary:
    """Check runs merged with legacy statuses for the head commit; anything unreadable
    degrades to an unavailable summary, never an error.
    """
    head = pr.head
    if head is None or not isinstance(head.sha, str) or not head.sha:
        return UNAVAILABLE_CHECKS
    try:
        commit = repository.get_commit(head.sha)
        raw_runs = first(commit.get_check_runs(), CHECK_RUNS_FETCH_LIMIT)
        raw_statuses = commit.get_combined_status().statuses
    except (GithubException, BadAttributeException, requests.RequestException):
        return UNAVAILABLE_CHECKS
    names_and_states: list[tuple[str, str]] = []
    for run in raw_runs:
        if isinstance(run.name, str):
            name = sanitize_line(run.name)
        else:
            name = ""
        names_and_states.append((name, _run_state(run.conclusion)))
    for status in raw_statuses:
        if isinstance(status.context, str):
            name = sanitize_line(status.context)
        else:
            name = ""
        names_and_states.append((name, _status_state(status.state)))
    passed = sum(1 for _, state in names_and_states if state == "passed")
    running = sum(1 for _, state in names_and_states if state == "running")
    failed_names = [name for name, state in names_and_states if state == "failed"]
    return CheckSummary(
        passed=passed,
        failed=len(failed_names),
        running=running,
        failed_names=tuple(failed_names[:FAILED_NAMES_LIMIT]),
        hidden_failed=max(0, len(failed_names) - FAILED_NAMES_LIMIT),
        truncated=len(raw_runs) >= CHECK_RUNS_FETCH_LIMIT,
    )


def _run_state(conclusion: object) -> str:
    """ "passed"/"failed"/"running" for a check run's conclusion; unknown shapes count as
    running rather than crying wolf.
    """
    if conclusion in _PASSED_CONCLUSIONS:
        return "passed"
    if conclusion in _FAILED_CONCLUSIONS:
        return "failed"
    return "running"


def _status_state(state: object) -> str:
    """ "passed"/"failed"/"running" for a legacy commit status."""
    if state == "success":
        return "passed"
    if state in ("failure", "error"):
        return "failed"
    return "running"

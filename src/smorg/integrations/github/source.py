"""Fetch pull requests from GitHub through PyGithub and map them to typed items."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from urllib.parse import urlsplit

import httpx
import requests
from github import (
    Auth,
    BadAttributeException,
    BadCredentialsException,
    Github,
    GithubException,
    RateLimitExceededException,
)
from github.GithubObject import GithubObject
from github.Issue import IssueSearchResult
from github.IssueComment import IssueComment
from github.PaginatedList import PaginatedList
from github.PullRequest import PullRequest as GithubPullRequest
from github.PullRequestReview import PullRequestReview
from github.Repository import Repository

from smorg.auth.store import Credentials
from smorg.core.contract import (
    AccessNotAllowed,
    AuthExpired,
    IntegrationError,
    Item,
    Malformed,
    Unavailable,
)
from smorg.core.text import sanitize_block, sanitize_line, truncate


class Category(StrEnum):
    """Which of the dashboard's buckets a pull request landed in."""

    NEEDS_YOUR_REVIEW = "needs your review"
    NEEDS_TEAM_REVIEW = "needs your team's review"
    DRAFT = "drafts"
    WAITING = "waiting review or actions"
    NEEDS_ACTION = "needs actions"
    READY_TO_MERGE = "ready to merge"


REQUEST_TIMEOUT_SECONDS = 30
RESULTS_PER_PAGE = 50
MAX_PER_QUERY = 50
MAX_RETRIES = 2

REVIEW_LIMIT = 5
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

GRAPHQL_URL = "https://api.github.com/graphql"
PROFILE_ID = "github-profile"
# A day the queried range does not cover; rendered blank, unlike a zero-contribution day.
ABSENT_DAY = -1
DAYS_PER_WEEK = 7

# The profile is decoration, not state: a constant stamp keeps it inert to the seen-store.
PROFILE_STAMP = datetime(1970, 1, 1, tzinfo=UTC)

_CONTRIBUTION_LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

_PROFILE_QUERY = """
query {
  viewer {
    login
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { firstDay contributionDays { weekday contributionLevel } }
      }
    }
  }
}
"""

BASE_QUERY = "is:pr is:open archived:false"

# First match wins: the broad queries sit last so each takes only what the ones above left,
# which is how "your team's review" and "waiting" are computed.
QUERIES: tuple[tuple[Category, str], ...] = (
    (Category.NEEDS_YOUR_REVIEW, "user-review-requested:@me"),
    (Category.NEEDS_TEAM_REVIEW, "review-requested:@me"),
    (Category.DRAFT, "author:@me draft:true"),
    (Category.NEEDS_ACTION, "author:@me draft:false review:changes_requested"),
    (Category.NEEDS_ACTION, "author:@me draft:false status:failure"),
    (Category.READY_TO_MERGE, "author:@me draft:false review:approved status:success"),
    (Category.WAITING, "author:@me draft:false"),
)

# How GitHub names an organization that requires SSO, in the body of its 403.
SAML_ENFORCEMENT = "saml enforcement"

# Where a review that was never submitted sorts. Timezone-aware to match GitHub's own stamps:
# sorting an aware and a naive datetime together raises.
NEVER_SUBMITTED = datetime.max.replace(tzinfo=UTC)


@dataclass(frozen=True)
class PullRequest(Item):
    number: int
    title: str
    repository: str
    author: str
    category: Category


@dataclass(frozen=True)
class ContributionWeek:
    """One week of the contribution calendar: its start date and seven day levels, Sun-Sat."""

    first_day: date
    levels: tuple[int, ...]


@dataclass(frozen=True)
class Profile(Item):
    """The signed-in user and their contribution calendar, or an unavailable placeholder."""

    login: str
    total_contributions: int
    weeks: tuple[ContributionWeek, ...]
    unavailable: bool = False


@dataclass(frozen=True)
class Review:
    author: str
    state: str
    submitted_at: datetime | None


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
class Comment:
    author: str
    submitted_at: datetime | None
    body: str


@dataclass(frozen=True)
class Newest[T]:
    """The newest slice of a list too long to show whole."""

    items: tuple[T, ...]
    hidden: int = 0
    hidden_is_lower_bound: bool = False


@dataclass(frozen=True)
class LineCounts:
    additions: int = ABSENT_COUNT
    deletions: int = ABSENT_COUNT
    changed_files: int = ABSENT_COUNT


@dataclass(frozen=True)
class PullRequestDetail:
    body: str
    base: str
    head: str
    reviews: Newest[Review]
    comments: Newest[Comment]
    counts: LineCounts
    checks: CheckSummary


def _message_of(error: GithubException) -> str:
    """The server's own explanation, when it sent a readable one."""
    data = error.data
    if not isinstance(data, dict):
        return ""
    message = data.get("message")
    if not isinstance(message, str):
        return ""
    return message


def _translated(error: GithubException) -> IntegrationError:
    """The IntegrationError matching what would fix the failure: a new token (401), access
    granted (403), a corrected query (422), or waiting (any other status).
    """
    if error.status == 401:
        return AuthExpired("GitHub rejected the stored token; it may have expired or been revoked")
    if error.status == 403:
        if SAML_ENFORCEMENT in _message_of(error).casefold():
            return AccessNotAllowed("the token is not authorized for this organization's SSO")
        return AccessNotAllowed(
            "the token cannot reach this repository; check its organization access and scopes"
        )
    if error.status == 422:
        # GitHub refused a query this app wrote.
        return Malformed(f"GitHub refused the search: {sanitize_line(_message_of(error))}")
    return Unavailable(f"GitHub returned HTTP {error.status}")


@contextmanager
def _github_errors() -> Iterator[None]:
    """Turn everything PyGithub and its transport raise into IntegrationError."""
    try:
        yield
    except BadCredentialsException as error:
        raise AuthExpired(
            "GitHub rejected the stored token; it may have expired or been revoked"
        ) from error
    except RateLimitExceededException as error:
        raise Unavailable("GitHub's rate limit is exhausted; it resets shortly") from error
    except BadAttributeException as error:
        raise Malformed(f"GitHub returned a field of an unexpected type: {error}") from error
    except GithubException as error:
        raise _translated(error) from error
    except requests.RequestException as error:
        raise Unavailable("could not reach GitHub") from error


def _client(credentials: Credentials, lazy: bool = False) -> Github:
    """A client for one call into GitHub.

    `lazy` stops an object built from an address it was handed from fetching its own payload
    before anything reads it. That is how the detail pane addresses a repository by name without
    paying a request for it.
    """
    return Github(
        auth=Auth.Token(credentials.access_token),
        timeout=REQUEST_TIMEOUT_SECONDS,
        per_page=RESULTS_PER_PAGE,
        retry=MAX_RETRIES,
        lazy=lazy,
        # PyGithub paces every request by default, which GitHub asks for between writes. This
        # integration doesn't write, and writes keep their own separate pacing regardless.
        seconds_between_requests=0,
    )


def _unavailable_profile() -> Profile:
    return Profile(
        id=PROFILE_ID,
        updated_at=PROFILE_STAMP,
        url="https://github.com",
        login="",
        total_contributions=0,
        weeks=(),
        unavailable=True,
    )


def _week_of(raw_week: object) -> ContributionWeek | None:
    """A week's start date and its seven day levels, Sun-Sat; ABSENT_DAY where the range has no
    day. None if misshapen.
    """
    if not isinstance(raw_week, dict):
        return None
    raw_first_day = raw_week.get("firstDay")
    if not isinstance(raw_first_day, str):
        return None
    try:
        first_day = date.fromisoformat(raw_first_day)
    except ValueError:
        return None
    raw_days = raw_week.get("contributionDays")
    if not isinstance(raw_days, list):
        return None
    levels = [ABSENT_DAY] * DAYS_PER_WEEK
    for raw_day in raw_days:
        if not isinstance(raw_day, dict):
            return None
        weekday = raw_day.get("weekday")
        level_name = raw_day.get("contributionLevel")
        if not isinstance(weekday, int) or not 0 <= weekday < DAYS_PER_WEEK:
            return None
        if not isinstance(level_name, str):
            return None
        level = _CONTRIBUTION_LEVELS.get(level_name)
        if level is None:
            return None
        levels[weekday] = level
    return ContributionWeek(first_day=first_day, levels=tuple(levels))


def _profile_of(payload: object) -> Profile:
    """A Profile parsed from the GraphQL response body; unavailable on any shape surprise."""
    if not isinstance(payload, dict):
        return _unavailable_profile()
    data = payload.get("data")
    if not isinstance(data, dict):
        return _unavailable_profile()
    viewer = data.get("viewer")
    if not isinstance(viewer, dict):
        return _unavailable_profile()
    login = viewer.get("login")
    collection = viewer.get("contributionsCollection")
    if not isinstance(login, str) or not isinstance(collection, dict):
        return _unavailable_profile()
    calendar = collection.get("contributionCalendar")
    if not isinstance(calendar, dict):
        return _unavailable_profile()
    total = calendar.get("totalContributions")
    raw_weeks = calendar.get("weeks")
    if not isinstance(total, int) or not isinstance(raw_weeks, list):
        return _unavailable_profile()
    weeks: list[ContributionWeek] = []
    for raw_week in raw_weeks:
        week = _week_of(raw_week)
        if week is None:
            return _unavailable_profile()
        weeks.append(week)
    if not login.strip():
        return _unavailable_profile()
    login_text = sanitize_line(login)
    profile_url = f"https://github.com/{login_text}"
    return Profile(
        id=PROFILE_ID,
        updated_at=PROFILE_STAMP,
        url=profile_url,
        login=login_text,
        total_contributions=total,
        weeks=tuple(weeks),
    )


def _query_profile(credentials: Credentials, http: httpx.Client) -> Profile:
    """The viewer's profile over GraphQL; any failure degrades to unavailable, never raises."""
    headers = {"Authorization": f"Bearer {credentials.access_token}"}
    try:
        response = http.post(GRAPHQL_URL, json={"query": _PROFILE_QUERY}, headers=headers)
    except httpx.HTTPError:
        return _unavailable_profile()
    if response.status_code != 200:
        return _unavailable_profile()
    try:
        payload = response.json()
    except ValueError:
        return _unavailable_profile()
    return _profile_of(payload)


def fetch(credentials: Credentials, http: httpx.Client) -> tuple[Item, ...]:
    """Every open pull request that is yours or waiting on you, newest first, then the profile."""
    found: dict[str, PullRequest] = {}
    # Closed on the way out: a client owns a connection pool, and a dashboard that refreshes
    # every time you look at it would otherwise leave one behind per refresh.
    with _client(credentials) as client:
        for category, qualifiers in QUERIES:
            for result in _search(client, f"{BASE_QUERY} {qualifiers}"):
                pr = _pull_request_of(result, category)
                # setdefault, not assignment: QUERIES is in precedence order, so the first
                # category to claim a pull request keeps it.
                found.setdefault(pr.id, pr)
    newest_first = sorted(found.values(), key=lambda pr: pr.updated_at, reverse=True)
    profile = _query_profile(credentials, http)
    items: list[Item] = list(newest_first)
    items.append(profile)
    return tuple(items)


def _first[T: GithubObject](results: PaginatedList[T], limit: int) -> list[T]:
    """Up to `limit` results. A PaginatedList pages as it is walked, so stopping the walk is
    what stops the paging.
    """
    found: list[T] = []
    for result in results:
        found.append(result)
        if len(found) >= limit:
            break
    return found


def _search(client: Github, query: str) -> list[IssueSearchResult]:
    with _github_errors():
        return _first(client.search_issues(query), MAX_PER_QUERY)


def _text_of(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise Malformed(f"{field!r} was {type(value).__name__}, expected a string")
    return value


def _moment_of(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise Malformed(f"{field!r} was {type(value).__name__}, expected a timestamp")
    return value


def _repository_of(repository_url: str) -> str:
    """The `owner/name` of a repository."""
    marker = "/repos/"
    path = urlsplit(repository_url).path
    if marker not in path:
        raise Malformed(f"a pull request named no repository: {sanitize_line(repository_url)}")
    name = path.split(marker, 1)[1].strip("/")
    if not name:
        raise Malformed(f"a pull request named no repository: {sanitize_line(repository_url)}")
    return name


def _author_of(result: IssueSearchResult) -> str:
    """The login of whoever opened the pull request, or "" for a deleted account."""
    user = result.user
    if user is None:
        return ""
    login = user.login
    if not isinstance(login, str):
        return ""
    return sanitize_line(login)


def _pull_request_of(result: IssueSearchResult, category: Category) -> PullRequest:
    with _github_errors():
        repository = _repository_of(_text_of(result.repository_url, "repository_url"))
        number = result.number
        if not isinstance(number, int):
            raise Malformed(f"'number' was {type(number).__name__}, expected an integer")
        return PullRequest(
            # Unique across every repository in the tab, and stable across refreshes — which
            # is what the seen-state keys off.
            id=f"{repository}#{number}",
            updated_at=_moment_of(result.updated_at, "updated_at"),
            url=_text_of(result.html_url, "html_url"),
            number=number,
            title=sanitize_line(_text_of(result.title, "title")),
            repository=repository,
            author=_author_of(result),
            category=category,
        )


def fetch_detail(credentials: Credentials, http: httpx.Client, item: Item) -> PullRequestDetail:
    """The selected pull request's expanded view: description, branches, line counts, checks,
    reviews, and the newest comments.
    """
    if not isinstance(item, PullRequest):
        raise Malformed(f"expected a pull request, got {type(item).__name__}")
    with _client(credentials, lazy=True) as client, _github_errors():
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
            reviews=_reviews_of(pr),
            comments=_comments_of(pr),
            counts=_counts_of(pr),
            checks=_checks_of(repository, pr),
        )


def _submitted_order(review: Review) -> datetime:
    """Pending reviews sort last."""
    if review.submitted_at is None:
        return NEVER_SUBMITTED
    return review.submitted_at


def _body_of(pr: GithubPullRequest) -> str:
    """The description, sanitized and capped, or "" if there is none."""
    raw = pr.body
    if not isinstance(raw, str):
        return ""
    return truncate(sanitize_block(raw, limit=None), BODY_LIMIT)


def _reviews_of(pr: GithubPullRequest) -> Newest[Review]:
    raw_reviews = _first(pr.get_reviews(), REVIEWS_FETCH_LIMIT)
    all_reviews = [_review_of(raw) for raw in raw_reviews]
    oldest_first = sorted(all_reviews, key=_submitted_order)
    return Newest(
        items=tuple(oldest_first[-REVIEW_LIMIT:]),
        hidden=max(0, len(raw_reviews) - REVIEW_LIMIT),
        hidden_is_lower_bound=len(raw_reviews) >= REVIEWS_FETCH_LIMIT,
    )


def _comments_of(pr: GithubPullRequest) -> Newest[Comment]:
    raw_comments = _first(pr.get_issue_comments(), COMMENTS_FETCH_LIMIT)
    all_comments = [_comment_of(raw) for raw in raw_comments]
    return Newest(
        items=tuple(all_comments[-COMMENT_LIMIT:]),
        hidden=max(0, len(all_comments) - COMMENT_LIMIT),
        hidden_is_lower_bound=len(raw_comments) >= COMMENTS_FETCH_LIMIT,
    )


def _review_of(raw: PullRequestReview) -> Review:
    """A typed Review; anything GitHub omitted degrades to "" or None."""
    author = raw.user
    if author is None or not isinstance(author.login, str):
        name = ""
    else:
        name = sanitize_line(author.login)
    if isinstance(raw.state, str):
        state = sanitize_line(raw.state)
    else:
        state = ""
    if isinstance(raw.submitted_at, datetime):
        submitted_at = raw.submitted_at
    else:
        submitted_at = None
    return Review(author=name, state=state, submitted_at=submitted_at)


def _count_of(value: object) -> int:
    """A non-negative count from the payload, or ABSENT_COUNT when missing or misshapen."""
    if not isinstance(value, int) or value < 0:
        return ABSENT_COUNT
    return value


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


def _checks_of(repository: Repository, pr: GithubPullRequest) -> CheckSummary:
    """Check runs merged with legacy statuses for the head commit; anything unreadable
    degrades to an unavailable summary, never an error.
    """
    head = pr.head
    if head is None or not isinstance(head.sha, str) or not head.sha:
        return UNAVAILABLE_CHECKS
    try:
        commit = repository.get_commit(head.sha)
        raw_runs = _first(commit.get_check_runs(), CHECK_RUNS_FETCH_LIMIT)
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

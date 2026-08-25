"""The list fetch: every open pull request across the account, bucketed by search query."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

import httpx
from github import Github
from github.Issue import IssueSearchResult

from smorg.auth.store import Credentials
from smorg.core.contract import Item, Malformed
from smorg.core.text import sanitize_line
from smorg.integrations.github.source.client import connect, first, github_errors
from smorg.integrations.github.source.profile import query_profile


class Category(StrEnum):
    """Which of the dashboard's buckets a pull request landed in."""

    NEEDS_YOUR_REVIEW = "needs your review"
    NEEDS_TEAM_REVIEW = "needs your team's review"
    DRAFT = "drafts"
    WAITING = "waiting review or ci"
    NEEDS_ACTION = "needs actions"
    READY_TO_MERGE = "ready to merge"


MAX_PER_QUERY = 50

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


@dataclass(frozen=True)
class PullRequest(Item):
    number: int
    title: str
    repository: str
    author: str
    category: Category


def fetch(credentials: Credentials, http: httpx.Client) -> tuple[Item, ...]:
    """Every open pull request that is yours or waiting on you, newest first, then the profile."""
    found: dict[str, PullRequest] = {}
    # Closed on the way out: a client owns a connection pool, and a dashboard that refreshes
    # every time you look at it would otherwise leave one behind per refresh.
    with connect(credentials) as client:
        for category, qualifiers in QUERIES:
            for result in _search(client, f"{BASE_QUERY} {qualifiers}"):
                pr = _pull_request_of(result, category)
                # setdefault, not assignment: QUERIES is in precedence order, so the first
                # category to claim a pull request keeps it.
                found.setdefault(pr.id, pr)
    newest_first = sorted(found.values(), key=lambda pr: pr.updated_at, reverse=True)
    profile = query_profile(credentials, http)
    items: list[Item] = list(newest_first)
    items.append(profile)
    return tuple(items)


def _search(client: Github, query: str) -> list[IssueSearchResult]:
    with github_errors():
        return first(client.search_issues(query), MAX_PER_QUERY)


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
    with github_errors():
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

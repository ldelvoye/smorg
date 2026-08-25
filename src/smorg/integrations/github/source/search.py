"""The list fetch: review-requested buckets from REST search, authored buckets from live
GraphQL fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

import httpx
from github import Github
from github.Issue import IssueSearchResult

from smorg.auth.store import Credentials
from smorg.core.contract import (
    AccessNotAllowed,
    AuthExpired,
    IntegrationError,
    Item,
    Malformed,
    Unavailable,
)
from smorg.core.text import sanitize_line
from smorg.integrations.github.source.client import (
    SAML_ENFORCEMENT,
    connect,
    first,
    github_errors,
    query_graphql,
)
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
# GraphQL search serves at most 100 nodes per page; one page is the authored cap.
AUTHORED_FETCH_LIMIT = 100

BASE_QUERY = "is:pr is:open archived:false"

# First match wins: the direct query outranks the team query, and both outrank the authored
# buckets _category_of computes.
QUERIES: tuple[tuple[Category, str], ...] = (
    (Category.NEEDS_YOUR_REVIEW, "user-review-requested:@me"),
    (Category.NEEDS_TEAM_REVIEW, "review-requested:@me"),
)

# The index's `status:`/`review:` qualifiers go stale, so this matches stable facts only and
# reads state from the live node fields.
_AUTHORED_QUERY = f"""
query {{
  search(query: "{BASE_QUERY} author:@me", type: ISSUE, first: {AUTHORED_FETCH_LIMIT}) {{
    nodes {{
      ... on PullRequest {{
        number
        title
        url
        updatedAt
        isDraft
        reviewDecision
        repository {{ nameWithOwner }}
        author {{ login }}
        commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{ state }} }} }} }}
      }}
    }}
  }}
}}
"""


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
    for pr in _authored_pull_requests(credentials, http):
        # setdefault again: a pull request the review queries claimed keeps their bucket.
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


def _int_of(value: object, field: str) -> int:
    if not isinstance(value, int):
        raise Malformed(f"{field!r} was {type(value).__name__}, expected an integer")
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
        number = _int_of(result.number, "number")
        return PullRequest(
            # Unique across every repository in the tab and stable across refreshes: what the
            # seen-state keys off.
            id=f"{repository}#{number}",
            updated_at=_moment_of(result.updated_at, "updated_at"),
            url=_text_of(result.html_url, "html_url"),
            number=number,
            title=sanitize_line(_text_of(result.title, "title")),
            repository=repository,
            author=_author_of(result),
            category=category,
        )


def _category_of(is_draft: bool, review_decision: str | None, rollup_state: str | None) -> Category:
    """The dashboard bucket for one authored pull request. A null review_decision (no review
    required) and a null rollup_state (no CI) both read as green; a repo without required
    reviews therefore never surfaces changes requested, and reads ready once CI is green.
    """
    if is_draft:
        return Category.DRAFT
    if review_decision == "CHANGES_REQUESTED":
        return Category.NEEDS_ACTION
    if rollup_state in {"FAILURE", "ERROR"}:
        return Category.NEEDS_ACTION
    review_is_green = review_decision == "APPROVED" or review_decision is None
    ci_is_green = rollup_state == "SUCCESS" or rollup_state is None
    if review_is_green and ci_is_green:
        return Category.READY_TO_MERGE
    return Category.WAITING


def _authored_repository_of(node: dict[str, object]) -> str:
    repository = node.get("repository")
    if not isinstance(repository, dict):
        raise Malformed("a pull request node named no 'repository'")
    name = repository.get("nameWithOwner")
    if not isinstance(name, str):
        raise Malformed("a pull request node named no 'repository.nameWithOwner'")
    return name


def _authored_author_of(node: dict[str, object]) -> str:
    """The login of whoever opened the pull request, or "" for a deleted account."""
    author = node.get("author")
    if not isinstance(author, dict):
        return ""
    login = author.get("login")
    if not isinstance(login, str):
        return ""
    return sanitize_line(login)


def _authored_is_draft_of(node: dict[str, object]) -> bool:
    is_draft = node.get("isDraft")
    if not isinstance(is_draft, bool):
        return False
    return is_draft


def _authored_review_decision_of(node: dict[str, object]) -> str | None:
    decision = node.get("reviewDecision")
    if not isinstance(decision, str):
        return None
    return decision


def _authored_rollup_state_of(node: dict[str, object]) -> str | None:
    """The head commit's rollup state, or None; a repo with no CI reports no rollup at all."""
    commits = node.get("commits")
    if not isinstance(commits, dict):
        return None
    commit_nodes = commits.get("nodes")
    if not isinstance(commit_nodes, list) or not commit_nodes:
        return None
    commit_node = commit_nodes[0]
    if not isinstance(commit_node, dict):
        return None
    commit = commit_node.get("commit")
    if not isinstance(commit, dict):
        return None
    rollup = commit.get("statusCheckRollup")
    if not isinstance(rollup, dict):
        return None
    state = rollup.get("state")
    if not isinstance(state, str):
        return None
    return state


def _authored_moment_of(value: object, field: str) -> datetime:
    text = _text_of(value, field)
    try:
        return datetime.fromisoformat(text)
    except ValueError as error:
        raise Malformed(f"{field!r} was not a parseable timestamp") from error


def _authored_pull_request_of(node: object) -> PullRequest:
    if not isinstance(node, dict):
        raise Malformed(f"a pull request node was {type(node).__name__}, expected an object")
    number = _int_of(node.get("number"), "number")
    title = _text_of(node.get("title"), "title")
    url = _text_of(node.get("url"), "url")
    updated_at = _authored_moment_of(node.get("updatedAt"), "updatedAt")
    name_with_owner = _authored_repository_of(node)
    category = _category_of(
        _authored_is_draft_of(node),
        _authored_review_decision_of(node),
        _authored_rollup_state_of(node),
    )
    return PullRequest(
        # Unique across every repository in the tab, and stable across refreshes — which
        # is what the seen-state keys off.
        id=f"{name_with_owner}#{number}",
        updated_at=updated_at,
        url=url,
        number=number,
        title=sanitize_line(title),
        repository=sanitize_line(name_with_owner),
        author=_authored_author_of(node),
        category=category,
    )


def _nodes_of(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        raise Malformed("GitHub's authored-search response was not a JSON object")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise Malformed("GitHub's authored-search response carried no 'data'")
    search = data.get("search")
    if not isinstance(search, dict):
        raise Malformed("GitHub's authored-search response carried no 'search'")
    nodes = search.get("nodes")
    if not isinstance(nodes, list):
        raise Malformed("GitHub's authored-search response carried no 'nodes' list")
    return nodes


def _authored_search_nodes(credentials: Credentials, http: httpx.Client) -> list[object]:
    """The authored search's raw nodes. A failure raises so the tab errors instead of
    rendering a partial inbox.
    """
    try:
        response = query_graphql(credentials, http, _AUTHORED_QUERY)
    except httpx.HTTPError as error:
        raise Unavailable("could not reach GitHub") from error
    if response.status_code == 401:
        raise AuthExpired("GitHub rejected the stored token; it may have expired or been revoked")
    if response.status_code == 403:
        raise _refused_access(response)
    if response.status_code != 200:
        raise Unavailable(f"GitHub returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as error:
        raise Malformed("GitHub's authored-search response was not valid JSON") from error
    try:
        return _nodes_of(payload)
    except Malformed:
        refusal = _refusal_of(payload)
        if refusal is None:
            raise
        raise refusal from None


def _refused_access(response: httpx.Response) -> AccessNotAllowed:
    """The 403's precise meaning: an SSO wall when the body names one, scopes otherwise."""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    message = ""
    if isinstance(payload, dict):
        raw_message = payload.get("message")
        if isinstance(raw_message, str):
            message = raw_message
    if SAML_ENFORCEMENT in message.casefold():
        return AccessNotAllowed("the token is not authorized for this organization's SSO")
    return AccessNotAllowed(
        "the token cannot reach this repository; check its organization access and scopes"
    )


def _refusal_of(payload: object) -> IntegrationError | None:
    """The body-level refusal GitHub reports with HTTP 200, or None when there is none."""
    if not isinstance(payload, dict):
        return None
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None
    first_error = errors[0]
    if not isinstance(first_error, dict):
        return Unavailable("GitHub's GraphQL API refused the search")
    error_type = first_error.get("type")
    if error_type in ("INSUFFICIENT_SCOPES", "FORBIDDEN"):
        return AccessNotAllowed(
            "the token cannot reach this repository; check its organization access and scopes"
        )
    if error_type == "RATE_LIMITED":
        return Unavailable("GitHub's rate limit is exhausted; it resets shortly")
    message = first_error.get("message")
    if isinstance(message, str) and message:
        return Unavailable(f"GitHub refused the search: {sanitize_line(message)}")
    return Unavailable("GitHub's GraphQL API refused the search")


def _authored_pull_requests(credentials: Credentials, http: httpx.Client) -> list[PullRequest]:
    """Every open pull request the viewer authored, bucketed by live node fields."""
    nodes = _authored_search_nodes(credentials, http)
    return [_authored_pull_request_of(node) for node in nodes]

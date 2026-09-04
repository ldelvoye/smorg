"""Fetch issues from Linear's MCP endpoint and map them to typed items."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from smorg.auth.store import Credentials
from smorg.core.contract import Item, Malformed, Newest
from smorg.core.mcp import McpSession
from smorg.core.shape import optional_string, required_string, timestamp
from smorg.core.text import sanitize_block, sanitize_line, truncate

ENDPOINT = "https://mcp.linear.app/mcp"

# Linear embeds machine tags in descriptions and comment bodies, e.g.
# <issue id="..." href="https://linear.app/...">ENG-123</issue>. Only these four known names are
# touched, so unrelated angle-bracket text (a code fence's own literal HTML, say) is left alone.
_LINEAR_TAG_NAMES = ("issue", "user", "project", "document", "pull-request")
_LINEAR_PAIRED_TAG = re.compile(
    r"<(" + "|".join(_LINEAR_TAG_NAMES) + r")\b([^>]*)>(.*?)</\1>", re.DOTALL
)
_LINEAR_LONE_TAG = re.compile(r"<(?:" + "|".join(_LINEAR_TAG_NAMES) + r")\b[^>]*/?>")
_HREF_ATTR = re.compile(r'href="([^"]*)"')

FIELDS = (
    "title",
    "status",
    "statusType",
    "updatedAt",
    "url",
    "team",
    "priority",
    "project",
)

ACTIVE_STATUS_TYPES = frozenset({"started", "unstarted"})

MAX_PAGES = 10

COMMENT_LIMIT = 5
COMMENTS_FETCH_LIMIT = 25
DESCRIPTION_LIMIT = 50_000
COMMENT_BODY_LIMIT = 10_000

SUB_ISSUE_FETCH_LIMIT = 50
SUB_ISSUE_FIELDS = ("id", "title", "status", "statusType", "priority")


@dataclass(frozen=True)
class Issue(Item):
    title: str
    status: str
    status_type: str
    team: str
    priority: str
    project: str


@dataclass(frozen=True)
class Comment:
    author: str
    body: str
    created_at: datetime


@dataclass(frozen=True)
class SubIssue:
    id: str
    title: str
    status: str
    status_type: str
    priority: str
    url: str = ""


@dataclass(frozen=True)
class RelatedIssue:
    id: str
    title: str
    url: str = ""


@dataclass(frozen=True)
class Link:
    title: str
    url: str


@dataclass(frozen=True)
class Transition:
    status: str
    status_type: str
    at: datetime


@dataclass(frozen=True)
class ParentSummary:
    id: str
    title: str
    status: str
    status_type: str


@dataclass(frozen=True)
class IssueDetail:
    description: str
    assignee: str
    creator: str
    labels: tuple[str, ...]
    project: str
    milestone: str
    due_date: str
    estimate: str
    parent: ParentSummary | None
    sub_issues: tuple[SubIssue, ...]
    blocked_by: tuple[RelatedIssue, ...]
    blocks: tuple[RelatedIssue, ...]
    related: tuple[RelatedIssue, ...]
    links: tuple[Link, ...]
    transitions: tuple[Transition, ...]
    comments: Newest[Comment]


def fetch(credentials: Credentials, http: httpx.Client) -> tuple[Issue, ...]:
    session = McpSession(ENDPOINT, credentials.access_token, http)

    issues: list[Issue] = []
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        arguments: dict[str, Any] = {
            "assignee": "me",
            "limit": 50,
            "orderBy": "updatedAt",
            "fields": list(FIELDS),
        }
        if cursor:
            arguments["cursor"] = cursor
        payload = session.call("list_issues", arguments)
        raw_issues = payload.get("issues")
        if not isinstance(raw_issues, list):
            raise Malformed("list_issues returned no issue list")
        issues.extend(_issue_of(raw) for raw in raw_issues)
        if not payload.get("hasNextPage"):
            break
        cursor = payload.get("cursor")
        if not isinstance(cursor, str) or not cursor:
            break

    active = [issue for issue in issues if issue.status_type in ACTIVE_STATUS_TYPES]
    newest_first = sorted(active, key=lambda issue: issue.updated_at, reverse=True)
    return tuple(newest_first)


def _priority_of(raw: dict[str, Any]) -> str:
    priority = raw.get("priority")
    if priority is None:
        return ""
    if not isinstance(priority, dict):
        raise Malformed(f"'priority' was {type(priority).__name__}, expected an object")
    return optional_string(priority, "name")


def _issue_of(raw: Any) -> Issue:
    if not isinstance(raw, dict):
        raise Malformed(f"an issue was {type(raw).__name__}, expected an object")
    return Issue(
        id=required_string(raw, "id"),
        updated_at=timestamp(raw, "updatedAt"),
        url=required_string(raw, "url"),
        title=required_string(raw, "title"),
        status=required_string(raw, "status"),
        status_type=required_string(raw, "statusType"),
        team=optional_string(raw, "team"),
        priority=_priority_of(raw),
        project=optional_string(raw, "project"),
    )


def fetch_detail(credentials: Credentials, http: httpx.Client, item: Item) -> IssueDetail:
    """The issue's expanded view: properties, parent, sub-issues, relations, links, and activity."""
    session = McpSession(ENDPOINT, credentials.access_token, http)
    issue_payload = session.call("get_issue", {"id": item.id, "includeRelations": True})
    comments_payload = session.call(
        "list_comments", {"issueId": item.id, "limit": COMMENTS_FETCH_LIMIT}
    )
    children_payload = session.call(
        "list_issues",
        {"parentId": item.id, "limit": SUB_ISSUE_FETCH_LIMIT, "fields": list(SUB_ISSUE_FIELDS)},
    )
    parent_id = optional_string(issue_payload, "parentId")
    if parent_id:
        parent_payload = session.call("get_issue", {"id": parent_id})
        parent = _parent_of(parent_payload)
    else:
        parent = None

    # Sanitize uncapped, then unwrap, then cap: unwrapping after capping could cut mid-tag and
    # leave one of our own <issue>/<user>/... fragments dangling in what the panel renders.
    sanitized = sanitize_block(optional_string(issue_payload, "description"), limit=None)
    description = truncate(_unwrap_linear_tags(sanitized), DESCRIPTION_LIMIT)
    relations = issue_payload.get("relations")
    if relations is None:
        relations = {}
    if not isinstance(relations, dict):
        raise Malformed(f"'relations' was {type(relations).__name__}, expected an object")
    url_base = _issue_url_base(item.url)
    return IssueDetail(
        description=description,
        assignee=_clean_optional(issue_payload, "assignee"),
        creator=_clean_optional(issue_payload, "createdBy"),
        labels=_labels_of(issue_payload),
        project=_clean_optional(issue_payload, "project"),
        milestone=_milestone_of(issue_payload),
        due_date=_due_date_of(issue_payload),
        estimate=_estimate_of(issue_payload),
        parent=parent,
        sub_issues=_sub_issues_of(children_payload, url_base),
        blocked_by=_related_of(relations, "blockedBy", url_base),
        blocks=_related_of(relations, "blocks", url_base),
        related=_related_of(relations, "relatedTo", url_base),
        links=_links_of(issue_payload),
        transitions=_transitions_of(issue_payload),
        comments=_comments_of(comments_payload),
    )


def _clean_optional(raw: dict[str, Any], key: str) -> str:
    value = optional_string(raw, key)
    if value:
        return sanitize_line(value)
    return ""


def _list_of(raw: dict[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise Malformed(f"{key!r} was {type(value).__name__}, expected a list")
    return value


def _labels_of(raw: dict[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []
    for label in _list_of(raw, "labels"):
        if not isinstance(label, str):
            raise Malformed(f"a label was {type(label).__name__}, expected a string")
        labels.append(sanitize_line(label))
    return tuple(labels)


def _milestone_of(raw: dict[str, Any]) -> str:
    milestone = raw.get("projectMilestone")
    if milestone is None:
        return ""
    if not isinstance(milestone, dict):
        raise Malformed(f"'projectMilestone' was {type(milestone).__name__}, expected an object")
    return _clean_optional(milestone, "name")


def _estimate_of(raw: dict[str, Any]) -> str:
    estimate = raw.get("estimate")
    if estimate is None:
        return ""
    if isinstance(estimate, bool) or not isinstance(estimate, (int, float)):
        raise Malformed(f"'estimate' was {type(estimate).__name__}, expected a number")
    return str(int(estimate))


def _due_date_of(raw: dict[str, Any]) -> str:
    """The ISO due date as Linear sends it, "" when unset; anything else is Malformed."""
    value = optional_string(raw, "dueDate")
    if not value:
        return ""
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise Malformed(f"'dueDate' was not a valid date ({sanitize_line(str(error))})") from error
    return value


def _parent_of(raw: dict[str, Any]) -> ParentSummary:
    return ParentSummary(
        id=sanitize_line(required_string(raw, "id")),
        title=sanitize_line(required_string(raw, "title")),
        status=sanitize_line(required_string(raw, "status")),
        status_type=required_string(raw, "statusType"),
    )


def _sub_issues_of(payload: dict[str, Any], url_base: str) -> tuple[SubIssue, ...]:
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        raise Malformed("list_issues returned no issue list")
    children: list[SubIssue] = []
    for raw in raw_issues:
        if not isinstance(raw, dict):
            raise Malformed(f"a sub-issue was {type(raw).__name__}, expected an object")
        identifier = sanitize_line(required_string(raw, "id"))
        children.append(
            SubIssue(
                id=identifier,
                title=sanitize_line(required_string(raw, "title")),
                status=sanitize_line(required_string(raw, "status")),
                status_type=required_string(raw, "statusType"),
                priority=_priority_of(raw),
                url=_https_of(f"{url_base}{identifier}"),
            )
        )
    return tuple(children)


def _issue_url_base(url: str) -> str:
    """ "https://linear.app/x/issue/ENG-1/slug" -> "https://linear.app/x/issue/"; "" if unknown."""
    marker = "/issue/"
    index = url.find(marker)
    if index == -1:
        return ""
    return url[: index + len(marker)]


def _related_of(relations: dict[str, Any], key: str, url_base: str) -> tuple[RelatedIssue, ...]:
    """Relations of one kind, each linking to the issue page its identifier resolves to."""
    related: list[RelatedIssue] = []
    for raw in _list_of(relations, key):
        if not isinstance(raw, dict):
            raise Malformed(f"a relation was {type(raw).__name__}, expected an object")
        identifier = sanitize_line(required_string(raw, "id"))
        related.append(
            RelatedIssue(
                id=identifier,
                title=sanitize_line(required_string(raw, "title")),
                url=_https_of(f"{url_base}{identifier}"),
            )
        )
    return tuple(related)


def _links_of(raw: dict[str, Any]) -> tuple[Link, ...]:
    """Attachments with an https url; a missing title falls back to the url itself."""
    links: list[Link] = []
    for attachment in _list_of(raw, "attachments"):
        if not isinstance(attachment, dict):
            raise Malformed(f"an attachment was {type(attachment).__name__}, expected an object")
        url = _https_of(optional_string(attachment, "url"))
        if not url:
            continue
        title = _clean_optional(attachment, "title")
        if not title:
            title = url
        links.append(Link(title=title, url=url))
    return tuple(links)


def _transitions_of(raw: dict[str, Any]) -> tuple[Transition, ...]:
    transitions: list[Transition] = []
    for entry in _list_of(raw, "stateHistory"):
        if not isinstance(entry, dict):
            raise Malformed(f"a history entry was {type(entry).__name__}, expected an object")
        state = entry.get("state")
        if not isinstance(state, dict):
            raise Malformed("a history entry had no state object")
        transitions.append(
            Transition(
                status=sanitize_line(required_string(state, "name")),
                status_type=required_string(state, "type"),
                at=timestamp(entry, "startedAt"),
            )
        )
    return tuple(transitions)


def _comments_of(payload: dict[str, Any]) -> Newest[Comment]:
    raw_comments = payload.get("comments")
    if not isinstance(raw_comments, list):
        raise Malformed("list_comments returned no comment list")
    all_comments = [_comment_of(raw) for raw in raw_comments]
    oldest_first = sorted(all_comments, key=lambda comment: comment.created_at)
    newest = oldest_first[-COMMENT_LIMIT:]
    more_on_server = bool(payload.get("hasNextPage"))
    return Newest(
        items=tuple(newest),
        hidden=max(0, len(raw_comments) - COMMENT_LIMIT),
        hidden_is_lower_bound=len(raw_comments) >= COMMENTS_FETCH_LIMIT or more_on_server,
    )


def _comment_of(raw: Any) -> Comment:
    if not isinstance(raw, dict):
        raise Malformed(f"a comment was {type(raw).__name__}, expected an object")
    author = raw.get("author")
    if author is None:
        name = ""
    elif isinstance(author, dict):
        raw_name = optional_string(author, "name")
        if raw_name:
            name = sanitize_line(raw_name)
        else:
            name = ""
    else:
        raise Malformed(f"'author' was {type(author).__name__}, expected an object")
    created_at = timestamp(raw, "createdAt")
    sanitized = sanitize_block(required_string(raw, "body"), limit=None)
    body = truncate(_unwrap_linear_tags(sanitized), COMMENT_BODY_LIMIT)
    return Comment(author=name, body=body, created_at=created_at)


def _unwrap_linear_tags(text: str) -> str:
    """Paired tags carrying a usable https href become markdown links labeled with their inner
    text; other paired tags degrade to the inner text alone, and lone tags are deleted.
    """
    rewritten = _LINEAR_PAIRED_TAG.sub(_rewrite_paired_tag, text)
    return _LINEAR_LONE_TAG.sub("", rewritten)


def _https_of(url: str) -> str:
    """The url when it is a printable, whitespace-free https url with a host, "" otherwise."""
    if not url.isprintable() or any(character.isspace() for character in url):
        return ""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        return ""
    return url


def _rewrite_paired_tag(match: re.Match[str]) -> str:
    attributes = match.group(2)
    inner = match.group(3)
    href_match = _HREF_ATTR.search(attributes)
    if href_match is None:
        return inner
    href = _https_of(href_match.group(1))
    if not href:
        return inner
    return f"[{inner}]({href})"

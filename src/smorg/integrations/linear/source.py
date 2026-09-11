"""Fetch issues from Linear's MCP endpoint and map them to typed items."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
# <issue id="..." href="https://linear.app/...">ENG-123</issue>. Only these five known names are
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

PROJECT_FIELDS = (
    "name",
    "summary",
    "url",
    "updatedAt",
    "startDate",
    "targetDate",
    "targetDateResolution",
    "priority",
    "lead",
    "status",
    "teams",
    "milestones",
)
_CLOSED_PROJECT_TYPES = frozenset({"completed", "canceled"})

ACTIVE_STATUS_TYPES = frozenset({"started", "unstarted"})

MAX_PAGES = 10

COMMENT_LIMIT = 5
COMMENTS_FETCH_LIMIT = 25
DESCRIPTION_LIMIT = 50_000
COMMENT_BODY_LIMIT = 10_000

SUB_ISSUE_FETCH_LIMIT = 50
SUB_ISSUE_FIELDS = ("id", "title", "status", "statusType", "priority")

PROJECT_ISSUE_FIELDS = (
    "id",
    "title",
    "status",
    "statusType",
    "priority",
    "url",
    "assignee",
    "parentId",
)
PROJECT_ISSUE_LIMIT = 250
PROJECT_ISSUE_PAGES = 2


@dataclass(frozen=True)
class Issue(Item):
    title: str
    status: str
    status_type: str
    team: str
    priority: str
    project: str


VIEWER_ID = "linear-viewer"
_VIEWER_STAMP = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Viewer(Item):
    """The signed-in user, riding in the item tuple the way GitHub's profile does."""

    name: str
    handle: str


@dataclass(frozen=True)
class Milestone:
    name: str
    target_date: str
    progress: int


@dataclass(frozen=True)
class Project(Item):
    """A project the viewer is a member of, with its milestones' progress."""

    name: str
    summary: str
    status: str
    status_type: str
    priority: str
    lead: str
    teams: tuple[str, ...]
    start_date: str
    target_date: str
    target_resolution: str
    milestones: tuple[Milestone, ...]


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
    url: str = ""


@dataclass(frozen=True)
class IssueDetail:
    description: str
    status: str
    status_type: str
    priority: str
    team: str
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


@dataclass(frozen=True)
class ProjectIssue:
    id: str
    title: str
    status: str
    status_type: str
    priority: str
    url: str
    assignee: str
    parent_id: str


@dataclass(frozen=True)
class ProjectDetail:
    """The project's page: its description, initiatives, milestones, and every issue."""

    description: str
    initiatives: tuple[str, ...]
    milestones: tuple[Milestone, ...]
    issues: tuple[ProjectIssue, ...]


def _pages(
    session: McpSession, tool: str, arguments: dict[str, Any], key: str, pages: int
) -> list[Any]:
    """Every raw entry under `key` across up to `pages` pages of `tool`, following the cursor."""
    entries: list[Any] = []
    cursor = ""
    for _ in range(pages):
        page_arguments = dict(arguments)
        if cursor:
            page_arguments["cursor"] = cursor
        payload = session.call(tool, page_arguments)
        raw_entries = payload.get(key)
        if not isinstance(raw_entries, list):
            raise Malformed(f"{tool} returned no {key} list")
        entries.extend(raw_entries)
        if not payload.get("hasNextPage"):
            break
        cursor = payload.get("cursor")
        if not isinstance(cursor, str) or not cursor:
            break
    return entries


def _fetch_projects(session: McpSession) -> list[Project]:
    arguments: dict[str, Any] = {
        "member": "me",
        "includeMilestones": True,
        "limit": 50,
        "orderBy": "updatedAt",
        "fields": list(PROJECT_FIELDS),
    }
    raw_projects = _pages(session, "list_projects", arguments, "projects", MAX_PAGES)
    projects: list[Project] = []
    for raw in raw_projects:
        project = _project_of(raw)
        if project.status_type in _CLOSED_PROJECT_TYPES:
            continue
        projects.append(project)
    return projects


def fetch(credentials: Credentials, http: httpx.Client) -> tuple[Item, ...]:
    session = McpSession(ENDPOINT, credentials.access_token, http)

    viewer_payload = session.call("get_user", {"query": "me"})
    viewer = _viewer_of(viewer_payload)

    projects = _fetch_projects(session)

    arguments: dict[str, Any] = {
        "assignee": "me",
        "limit": 50,
        "orderBy": "updatedAt",
        "fields": list(FIELDS),
    }
    raw_issues = _pages(session, "list_issues", arguments, "issues", MAX_PAGES)
    issues = [_issue_of(raw) for raw in raw_issues]

    active = [issue for issue in issues if issue.status_type in ACTIVE_STATUS_TYPES]
    newest_first = sorted(active, key=lambda issue: issue.updated_at, reverse=True)
    items: list[Item] = [viewer, *projects]
    items.extend(newest_first)
    return tuple(items)


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


def _person_of(raw: dict[str, Any], key: str) -> str:
    person = raw.get(key)
    if not isinstance(person, dict):
        return ""
    return _clean_optional(person, "name")


def _project_status_of(raw: dict[str, Any]) -> tuple[str, str]:
    status = raw.get("status")
    if not isinstance(status, dict):
        raise Malformed(f"'status' was {type(status).__name__}, expected an object")
    name = required_string(status, "name")
    status_type = optional_string(status, "type")
    return name, status_type


def _team_keys_of(raw: dict[str, Any]) -> tuple[str, ...]:
    teams = raw.get("teams")
    if not isinstance(teams, list):
        return ()
    keys: list[str] = []
    for team in teams:
        if not isinstance(team, dict):
            raise Malformed(f"a team was {type(team).__name__}, expected an object")
        keys.append(optional_string(team, "key"))
    return tuple(keys)


def _progress_of(raw: dict[str, Any]) -> int:
    text = optional_string(raw, "progress")
    digits = text.removesuffix("%").strip()
    if not digits.isdigit():
        return 0
    return int(digits)


def _project_milestone_of(raw: Any) -> Milestone:
    if not isinstance(raw, dict):
        raise Malformed(f"a milestone was {type(raw).__name__}, expected an object")
    name = required_string(raw, "name")
    return Milestone(
        name=sanitize_line(name),
        target_date=optional_string(raw, "targetDate"),
        progress=_progress_of(raw),
    )


def _project_milestones_of(raw: dict[str, Any]) -> tuple[Milestone, ...]:
    raw_milestones = raw.get("milestones")
    if raw_milestones is None:
        return ()
    if not isinstance(raw_milestones, list):
        raise Malformed(f"'milestones' was {type(raw_milestones).__name__}, expected a list")
    milestones: list[Milestone] = []
    for raw_milestone in raw_milestones:
        milestones.append(_project_milestone_of(raw_milestone))
    return tuple(milestones)


def _project_of(raw: Any) -> Project:
    if not isinstance(raw, dict):
        raise Malformed(f"a project was {type(raw).__name__}, expected an object")
    status, status_type = _project_status_of(raw)
    name = required_string(raw, "name")
    return Project(
        id=required_string(raw, "id"),
        updated_at=timestamp(raw, "updatedAt"),
        url=required_string(raw, "url"),
        name=sanitize_line(name),
        summary=_clean_optional(raw, "summary"),
        status=status,
        status_type=status_type,
        priority=_priority_of(raw),
        lead=_person_of(raw, "lead"),
        teams=_team_keys_of(raw),
        start_date=optional_string(raw, "startDate"),
        target_date=optional_string(raw, "targetDate"),
        target_resolution=optional_string(raw, "targetDateResolution"),
        milestones=_project_milestones_of(raw),
    )


def _viewer_of(raw: Any) -> Viewer:
    if not isinstance(raw, dict):
        raise Malformed("get_user returned no user")
    name = required_string(raw, "name")
    display_name = optional_string(raw, "displayName")
    if display_name:
        handle = display_name
    else:
        handle = name
    return Viewer(
        id=VIEWER_ID,
        updated_at=_VIEWER_STAMP,
        url="https://linear.app",
        name=name,
        handle=handle,
    )


def _description_of(payload: dict[str, Any]) -> str:
    raw_description = optional_string(payload, "description")
    sanitized = sanitize_block(raw_description, limit=None)
    unwrapped = _unwrap_linear_tags(sanitized)
    return truncate(unwrapped, DESCRIPTION_LIMIT)


def _project_issue_of(raw: Any) -> ProjectIssue:
    if not isinstance(raw, dict):
        raise Malformed(f"an issue was {type(raw).__name__}, expected an object")
    title = required_string(raw, "title")
    return ProjectIssue(
        id=required_string(raw, "id"),
        title=sanitize_line(title),
        status=required_string(raw, "status"),
        status_type=required_string(raw, "statusType"),
        priority=_priority_of(raw),
        url=required_string(raw, "url"),
        assignee=_person_of(raw, "assignee"),
        parent_id=optional_string(raw, "parentId"),
    )


def _initiatives_of(raw: dict[str, Any]) -> tuple[str, ...]:
    initiatives = raw.get("initiatives")
    if not isinstance(initiatives, list):
        return ()
    names: list[str] = []
    for initiative in initiatives:
        if not isinstance(initiative, dict):
            raise Malformed(f"an initiative was {type(initiative).__name__}, expected an object")
        names.append(_clean_optional(initiative, "name"))
    return tuple(names)


def _fetch_project_issues(session: McpSession, project: Project) -> tuple[ProjectIssue, ...]:
    arguments: dict[str, Any] = {
        "project": project.id,
        "limit": PROJECT_ISSUE_LIMIT,
        "orderBy": "updatedAt",
        "fields": list(PROJECT_ISSUE_FIELDS),
    }
    raw_issues = _pages(session, "list_issues", arguments, "issues", PROJECT_ISSUE_PAGES)
    issues = [_project_issue_of(raw) for raw in raw_issues]
    return tuple(issues)


def _fetch_project_detail(session: McpSession, project: Project) -> ProjectDetail:
    payload = session.call("get_project", {"query": project.id, "includeMilestones": True})
    if not isinstance(payload, dict):
        raise Malformed("get_project returned no project")
    description = _description_of(payload)
    return ProjectDetail(
        description=description,
        initiatives=_initiatives_of(payload),
        milestones=_project_milestones_of(payload),
        issues=_fetch_project_issues(session, project),
    )


def _fetch_issue_detail(session: McpSession, item: Item) -> IssueDetail:
    """The issue's expanded view: properties, parent, sub-issues, relations, links, and activity."""
    issue_payload = session.call("get_issue", {"id": item.id, "includeRelations": True})
    comments_payload = session.call(
        "list_comments", {"issueId": item.id, "limit": COMMENTS_FETCH_LIMIT}
    )
    children_payload = session.call(
        "list_issues",
        {"parentId": item.id, "limit": SUB_ISSUE_FETCH_LIMIT, "fields": list(SUB_ISSUE_FIELDS)},
    )
    url_base = _issue_url_base(item.url)
    parent_id = optional_string(issue_payload, "parentId")
    if parent_id:
        parent_payload = session.call("get_issue", {"id": parent_id})
        parent = _parent_of(parent_payload, url_base)
    else:
        parent = None

    # Sanitize uncapped, then unwrap, then cap: unwrapping after capping could cut mid-tag and
    # leave one of our own <issue>/<user>/... fragments dangling in what the panel renders.
    description = _description_of(issue_payload)
    relations = issue_payload.get("relations")
    if relations is None:
        relations = {}
    if not isinstance(relations, dict):
        raise Malformed(f"'relations' was {type(relations).__name__}, expected an object")
    return IssueDetail(
        description=description,
        status=sanitize_line(required_string(issue_payload, "status")),
        status_type=required_string(issue_payload, "statusType"),
        priority=_priority_of(issue_payload),
        team=_clean_optional(issue_payload, "team"),
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


def fetch_detail(
    credentials: Credentials, http: httpx.Client, item: Item
) -> IssueDetail | ProjectDetail:
    """The item's expanded view: an issue's page, or a project's page with all its issues."""
    session = McpSession(ENDPOINT, credentials.access_token, http)
    if isinstance(item, Project):
        return _fetch_project_detail(session, item)
    return _fetch_issue_detail(session, item)


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
    is_whole = float(estimate).is_integer()
    if is_whole:
        return str(int(estimate))
    return str(estimate)


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


def _parent_of(raw: dict[str, Any], url_base: str) -> ParentSummary:
    identifier = sanitize_line(required_string(raw, "id"))
    return ParentSummary(
        id=identifier,
        title=sanitize_line(required_string(raw, "title")),
        status=sanitize_line(required_string(raw, "status")),
        status_type=required_string(raw, "statusType"),
        url=_https_of(f"{url_base}{identifier}"),
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

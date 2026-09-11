"""The project's issues: status groups with the sub-issue tree under every in-flight root."""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static

from smorg.integrations.linear.glyphs import priority_rank, status_color, status_rank
from smorg.integrations.linear.navigation import format_target_row, target_of_project_issue
from smorg.integrations.linear.source import ProjectDetail, ProjectIssue
from smorg.integrations.linear.views import LinearView
from smorg.integrations.linear.views.issue import _BACK_HINT_PREFIX
from smorg.integrations.linear.views.issues import _format_group_title
from smorg.shell.cards import SELECTED_MARK, format_card, format_card_title
from smorg.shell.cursor import clamp_cursor, step_cursor
from smorg.shell.format import SELECTED_STYLE, plain_lines, truncating
from smorg.shell.terminal_palette import StatusColors
from smorg.shell.view_host import GatedBodyView

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

_IN_FLIGHT_TYPES = frozenset({"started", "unstarted"})
_DONE_TYPES = frozenset({"completed", "canceled", "duplicate"})
_BRANCH = "├─ "
_LAST_BRANCH = "└─ "
_CONTINUE = "│  "
_GAP = "   "
_ASSIGNEE_WIDTH = 8

_CARD_CHROME = 4


@dataclass(frozen=True)
class TreeRow:
    issue: ProjectIssue
    depth: int
    prefix: str


@dataclass(frozen=True)
class _StatusTallies:
    counts: dict[str, int]
    in_flight: tuple[tuple[str, str, int], ...]
    backlog: int
    done: int


def _row_key(issue: ProjectIssue) -> tuple[int, str, int, str]:
    return (
        status_rank(issue.status, issue.status_type),
        issue.status.casefold(),
        priority_rank(issue.priority),
        issue.id,
    )


def _children_by_parent(issues: tuple[ProjectIssue, ...]) -> dict[str, list[ProjectIssue]]:
    ids = {issue.id for issue in issues}
    children: dict[str, list[ProjectIssue]] = {}
    for issue in issues:
        if not issue.parent_id or issue.parent_id not in ids:
            continue
        siblings = children.setdefault(issue.parent_id, [])
        siblings.append(issue)
    for siblings in children.values():
        siblings.sort(key=_row_key)
    return children


def _has_in_flight_ancestor(issue: ProjectIssue, by_id: dict[str, ProjectIssue]) -> bool:
    seen: set[str] = set()
    parent_id = issue.parent_id
    while parent_id and parent_id in by_id and parent_id not in seen:
        seen.add(parent_id)
        parent = by_id[parent_id]
        if parent.status_type in _IN_FLIGHT_TYPES:
            return True
        parent_id = parent.parent_id
    return False


def _subtree(
    issue: ProjectIssue,
    depth: int,
    lead: str,
    children: dict[str, list[ProjectIssue]],
    rows: list[TreeRow],
) -> None:
    siblings = children.get(issue.id)
    if siblings is None:
        return
    last_index = len(siblings) - 1
    for index, child in enumerate(siblings):
        if index == last_index:
            branch = _LAST_BRANCH
            deeper = _GAP
        else:
            branch = _BRANCH
            deeper = _CONTINUE
        rows.append(TreeRow(child, depth + 1, lead + branch))
        _subtree(child, depth + 1, lead + deeper, children, rows)


def issue_tree(
    issues: tuple[ProjectIssue, ...],
) -> tuple[tuple[str, str, tuple[TreeRow, ...]], ...]:
    """(status, status type, rows) per in-flight status in rank order: each root, then its whole
    subtree beneath it."""
    by_id = {issue.id: issue for issue in issues}
    children = _children_by_parent(issues)
    roots: list[ProjectIssue] = []
    for issue in issues:
        if issue.status_type not in _IN_FLIGHT_TYPES:
            continue
        if _has_in_flight_ancestor(issue, by_id):
            continue
        roots.append(issue)
    roots.sort(key=_row_key)
    groups: list[tuple[str, str, tuple[TreeRow, ...]]] = []
    for root in roots:
        rows: list[TreeRow] = [TreeRow(root, 0, "")]
        _subtree(root, 0, "", children, rows)
        last_group = None
        if groups:
            last_group = groups[-1]
        if last_group is not None and last_group[0] == root.status:
            groups[-1] = (root.status, root.status_type, last_group[2] + tuple(rows))
        else:
            groups.append((root.status, root.status_type, tuple(rows)))
    return tuple(groups)


def _status_tallies(issues: tuple[ProjectIssue, ...]) -> _StatusTallies:
    counts: dict[str, int] = {}
    in_flight_counts: dict[str, int] = {}
    in_flight_types: dict[str, str] = {}
    backlog = 0
    done = 0
    for issue in issues:
        seen_so_far = counts.get(issue.status, 0)
        counts[issue.status] = seen_so_far + 1
        if issue.status_type in _IN_FLIGHT_TYPES:
            seen_in_flight = in_flight_counts.get(issue.status, 0)
            in_flight_counts[issue.status] = seen_in_flight + 1
            in_flight_types[issue.status] = issue.status_type
        elif issue.status_type in _DONE_TYPES:
            done += 1
        elif issue.status_type == "backlog":
            backlog += 1
    ranked: list[tuple[int, str, str]] = []
    for status, status_type in in_flight_types.items():
        rank = status_rank(status, status_type)
        ranked.append((rank, status.casefold(), status))
    ranked.sort()
    in_flight: list[tuple[str, str, int]] = []
    for _, _, status in ranked:
        in_flight.append((status, in_flight_types[status], in_flight_counts[status]))
    return _StatusTallies(counts=counts, in_flight=tuple(in_flight), backlog=backlog, done=done)


def _format_issue_counts(tallies: _StatusTallies, colors: StatusColors, accent: str) -> Text:
    entries: list[tuple[str, str]] = []
    for status, status_type, count in tallies.in_flight:
        color = status_color(status, status_type, colors, accent)
        label = f"{count} {status.lower()}"
        entries.append((label, color))
    if tallies.backlog:
        entries.append((f"{tallies.backlog} backlog", "dim"))
    if tallies.done:
        entries.append((f"{tallies.done} done", "dim"))
    line = Text()
    for index, (label, style) in enumerate(entries):
        if index > 0:
            line.append(" · ", style="dim")
        line.append(label, style=style)
    return truncating(line)


def _format_assignee(assignee: str, viewer_name: str, accent: str) -> Text:
    if not assignee:
        blank = " " * _ASSIGNEE_WIDTH
        return Text(blank)
    if assignee == viewer_name:
        mine = "you".rjust(_ASSIGNEE_WIDTH)
        return Text(mine, style=accent)
    words = assignee.split()
    first_name = words[0]
    clipped = first_name[:_ASSIGNEE_WIDTH]
    padded = clipped.rjust(_ASSIGNEE_WIDTH)
    return Text(padded, style="dim")


def _format_tree_row(
    row: TreeRow, selected: bool, viewer_name: str, colors: StatusColors, accent: str, budget: int
) -> Text:
    line = Text()
    if selected:
        line.append(SELECTED_MARK, style=SELECTED_STYLE)
    else:
        line.append(" ")
    line.append(" ")
    line.append(row.prefix, style="dim")
    muted = row.issue.status_type not in _IN_FLIGHT_TYPES
    target = target_of_project_issue(row.issue)
    body = format_target_row(target, colors, accent, muted)
    if selected:
        title_start = len(body.plain) - len(row.issue.title)
        body.stylize(SELECTED_STYLE, title_start, len(body.plain))
    line.append_text(body)
    title_width = budget - _ASSIGNEE_WIDTH - 1
    line.truncate(title_width, overflow="ellipsis", pad=True)
    assignee = _format_assignee(row.issue.assignee, viewer_name, accent)
    line.append_text(assignee)
    return truncating(line)


def _format_issues_card(
    detail: ProjectDetail,
    viewer_name: str,
    colors: StatusColors,
    accent: str,
    cursor: int,
    budget: int,
) -> RenderableType:
    title = format_card_title(f"issues ({len(detail.issues)})", accent)
    if not detail.issues:
        return format_card(title, [Text("no issues", style="dim")])
    inner = budget - _CARD_CHROME
    tallies = _status_tallies(detail.issues)
    body: list[RenderableType] = [_format_issue_counts(tallies, colors, accent)]
    position = 0
    for status, status_type, rows in issue_tree(detail.issues):
        body.append(Text())
        count = tallies.counts[status]
        body.append(_format_group_title(status, status_type, count, colors, accent))
        for row in rows:
            selected = position == cursor
            body.append(_format_tree_row(row, selected, viewer_name, colors, accent, inner))
            position += 1
    return format_card(title, body)


class LinearProjectIssues(GatedBodyView["LinearPanel"]):
    BINDINGS = [
        Binding("up", "cursor_up", "select issue", show=False),
        Binding("down", "cursor_down", "select issue", show=False),
        Binding("o", "open_selected", "open in Linear", show=False),
        Binding("enter", "open_issue", "view issue", show=False),
        Binding("escape", "back_to_project", "back to project", show=False),
    ]
    DEFAULT_CSS = """
    LinearProjectIssues { width: 100%; max-width: 120; }
    """

    def detail(self) -> ProjectDetail | None:
        project = self.panel.viewed_project
        if project is None:
            return None
        raw = self.panel.detail_for(project)
        if isinstance(raw, ProjectDetail):
            return raw
        return None

    def _tree_rows(self) -> tuple[TreeRow, ...]:
        detail = self.detail()
        if detail is None:
            return ()
        flattened: list[TreeRow] = []
        for _, _, rows in issue_tree(detail.issues):
            flattened.extend(rows)
        return tuple(flattened)

    def _viewer_name(self) -> str:
        viewer = self.panel.viewer()
        if viewer is None:
            return ""
        return viewer.name

    def _budget(self) -> int:
        if not self.is_mounted:
            return 80
        body = self.query_one("#body", Static)
        if body.size.width > 0:
            return body.size.width
        return 80

    def selected_issue(self) -> ProjectIssue | None:
        rows = self._tree_rows()
        if not rows:
            return None
        index = clamp_cursor(self.cursor, len(rows))
        return rows[index].issue

    def _move(self, offset: int) -> None:
        rows = self._tree_rows()
        if not rows:
            return
        self.cursor = step_cursor(self.cursor, offset, len(rows))
        self.panel.refresh()
        self.scroll_to_selection()

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def action_open_selected(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            return
        webbrowser.open(issue.url)

    def action_open_issue(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            return
        target = target_of_project_issue(issue)
        self.panel.open_target(target)

    def action_back_to_project(self) -> None:
        self.panel.show_view(LinearView.PROJECT)

    def render_view(self) -> RenderableType:
        project = self.panel.viewed_project
        if project is None:
            return Text()
        hint = Text(f"{_BACK_HINT_PREFIX}{project.name}", style="dim")
        parts: list[RenderableType] = [hint, Text()]
        detail = self.detail()
        error = self.panel.detail_error_for(project)
        if detail is None and error is not None:
            parts.append(Text(f"could not load: {error}"))
            return Group(*parts)
        if detail is None:
            parts.append(Text("loading…", style="dim"))
            return Group(*parts)
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        rows = self._tree_rows()
        cursor = clamp_cursor(self.cursor, len(rows))
        viewer_name = self._viewer_name()
        budget = self._budget()
        parts.append(_format_issues_card(detail, viewer_name, colors, accent, cursor, budget))
        return Group(*parts)

    def content_lines(self) -> list[str]:
        return plain_lines(self.render_view())

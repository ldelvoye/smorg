"""One list of your issues, grouped by status in actionability order."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from smorg.integrations.linear.glyphs import (
    PRIORITY_WIDTH,
    format_priority,
    status_color,
    status_disc,
)
from smorg.integrations.linear.palette import accent_for_background
from smorg.integrations.linear.source import Issue
from smorg.shell.cards import format_card, format_card_title, format_marks
from smorg.shell.cursor import clamp_cursor, step_cursor
from smorg.shell.format import age, plain_lines, truncating
from smorg.shell.panel import PanelState, ViewBody
from smorg.shell.terminal_palette import StatusColors
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

# Ordered by actionability: doing, shepherding, queued, stuck.
_STATUS_RANKS = {"in progress": 0, "in review": 1, "todo": 3, "blocked": 5}

# The meta line starts under the id column: marks (3), priority (3), and their two separators.
_META_INDENT = " " * 8


def _status_rank(status: str, status_type: str) -> int:
    known = _STATUS_RANKS.get(status.casefold())
    if known is not None:
        return known
    if status_type == "started":
        return 2
    return 4


def _format_group_title(
    status: str, status_type: str, count: int, colors: StatusColors, accent: str
) -> Text:
    color = status_color(status, status_type, colors, accent)
    disc = status_disc(status, status_type)
    if color == "dim":
        tint = ""
    else:
        tint = color
    return format_card_title(f"{disc} {status} ({count})", tint)


def _format_row_meta(issue: Issue) -> Text:
    meta = Text(style="dim")
    if issue.project:
        meta.append(issue.project)
        meta.append(" · ")
    meta.append(age(issue.updated_at))
    return meta


def _status_groups(issues: tuple[Issue, ...]) -> list[tuple[str, str, list[Issue]]]:
    """Runs of consecutive same-status issues, in the order _grouped() already sorted them into."""
    groups: list[tuple[str, str, list[Issue]]] = []
    current_status = ""
    current_members: list[Issue] = []
    for issue in issues:
        if issue.status != current_status:
            current_status = issue.status
            current_members = []
            groups.append((issue.status, issue.status_type, current_members))
        current_members.append(issue)
    return groups


class LinearIssues(Vertical, HostedView):
    BINDINGS = [
        Binding("up", "cursor_up", "select issue", show=False),
        Binding("down", "cursor_down", "select issue", show=False),
        Binding("o", "open_selected", "open in Linear", show=False),
        Binding("enter", "open_issue", "view issue", show=False),
    ]
    can_focus = True

    DEFAULT_CSS = """
    LinearIssues { width: 100%; max-width: 120; }
    LinearIssues > #body { height: 1fr; }
    """

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__()
        self.panel = panel
        self.cursor = 0

    def compose(self) -> ComposeResult:
        yield ViewBody(self._render_body, id="body")

    def _render_body(self) -> RenderableType:
        if self.panel.state is PanelState.READY:
            return self.render_view()
        return self.panel.body_text()

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#body", Static).refresh()

    def selected_item(self) -> Issue | None:
        issues = self._grouped()
        if not issues:
            return None
        index = clamp_cursor(self.cursor, len(issues))
        return issues[index]

    def selected_url(self) -> str | None:
        issue = self.selected_item()
        if issue is None:
            return None
        return issue.url

    def _grouped(self) -> tuple[Issue, ...]:
        """Issues as one ordered sequence: status groups in fixed rank order, so a refresh never
        reshuffles them. The cursor moves through this same sequence.
        """
        groups: dict[str, list[Issue]] = {}
        for issue in self.panel.issues():
            groups.setdefault(issue.status, []).append(issue)
        ordered_statuses = sorted(
            groups,
            key=lambda status: (
                _status_rank(status, groups[status][0].status_type),
                status.casefold(),
            ),
        )
        ordered_issues: list[Issue] = []
        for status in ordered_statuses:
            ordered_issues.extend(groups[status])
        return tuple(ordered_issues)

    def _move(self, offset: int) -> None:
        issues = self._grouped()
        if not issues:
            return
        self.cursor = step_cursor(self.cursor, offset, len(issues))
        self.panel.refresh()

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def action_open_selected(self) -> None:
        issue = self.selected_item()
        if issue is None:
            return
        webbrowser.open(issue.url)
        self.panel.mark_seen(issue)

    def render_view(self) -> RenderableType:
        issues = self._grouped()
        cursor = clamp_cursor(self.cursor, len(issues))
        if issues:
            selected = issues[cursor]
        else:
            selected = None
        colors = self.panel.status_colors()
        accent = accent_for_background(self.panel._terminal_background())
        # One width for the whole list, so the title column never shifts at a group boundary.
        id_width = max((len(issue.id) for issue in issues), default=0)
        parts: list[RenderableType] = []
        for index, (status, status_type, members) in enumerate(_status_groups(issues)):
            if index > 0:
                parts.append(Text())
            title = _format_group_title(status, status_type, len(members), colors, accent)
            body: list[RenderableType] = []
            for issue in members:
                if body:
                    body.append(Text())
                head, meta = self._format_cell(issue, issue is selected, id_width, colors, accent)
                body.append(head)
                body.append(meta)
            parts.append(format_card(title, body))
        return Group(*parts)

    def _format_cell(
        self, issue: Issue, selected: bool, id_width: int, colors: StatusColors, accent: str
    ) -> tuple[Text, Text]:
        """The issue's two lines: marks, priority, id, disc, and title, then its dim meta."""
        head = Text()
        changed = self.panel.seen.is_changed(self.panel.integration_id, issue)
        head.append_text(format_marks(selected, changed, accent))
        head.append(" ")
        stage_color = status_color(issue.status, issue.status_type, colors, accent)
        priority = format_priority(issue.priority, colors, stage_color)
        head.append_text(priority)
        head.append(" " * (PRIORITY_WIDTH - len(priority.plain) + 1))
        head.append(issue.id.ljust(id_width), style="dim")
        head.append(" ")
        disc = status_disc(issue.status, issue.status_type)
        head.append(disc, style=stage_color)
        head.append(" ")
        if selected:
            head.append(issue.title, style="bold")
        else:
            head.append(issue.title)

        meta = Text(_META_INDENT)
        meta.append_text(_format_row_meta(issue))
        return truncating(head), truncating(meta)

    def content_lines(self) -> list[str]:
        """render_view flattened to plain text, so the two cannot drift apart."""
        return plain_lines(self.render_view())

    def action_open_issue(self) -> None:
        issue = self.selected_item()
        if issue is None:
            return
        self.panel.open_issue(issue)

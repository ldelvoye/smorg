"""One list of your issues, grouped by status in actionability order."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.binding import Binding

from smorg.integrations.linear.glyphs import (
    PRIORITY_WIDTH,
    format_priority,
    status_color,
    status_disc,
    status_rank,
)
from smorg.integrations.linear.source import Issue
from smorg.integrations.linear.views import LinearView
from smorg.shell.cards import CARD_CHROME, format_card, format_card_title, format_marks
from smorg.shell.cursor import clamp_cursor, step_cursor
from smorg.shell.format import age, plain_lines, truncating
from smorg.shell.marquee import MARQUEE_STYLE, marquee_overflow, marquee_window
from smorg.shell.terminal_palette import StatusColors
from smorg.shell.view_host import GatedBodyView

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

# The meta line starts under the id column: marks (3), priority (3), and their two separators.
_META_INDENT = " " * 8


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


def _id_width(issues: tuple[Issue, ...]) -> int:
    """One id column width for the whole list, so the title column never shifts between groups."""
    widths = [len(issue.id) for issue in issues]
    if not widths:
        return 0
    return max(widths)


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


class LinearIssues(GatedBodyView["LinearPanel"]):
    BINDINGS = [
        Binding("up", "cursor_up", "select issue", show=False),
        Binding("down", "cursor_down", "select issue", show=False),
        Binding("o", "open_selected", "open in Linear", show=False),
        Binding("enter", "open_issue", "view issue", show=False),
        Binding("escape", "back_to_menu", "back to menu", show=False),
    ]
    DEFAULT_CSS = """
    LinearIssues { width: 100%; max-width: 120; }
    """

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
                status_rank(status, groups[status][0].status_type),
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
        self.marquee.reset()
        self.panel.refresh()
        self.scroll_to_selection()

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

    def action_back_to_menu(self) -> None:
        self.panel.show_view(LinearView.MENU)

    def render_view(self) -> RenderableType:
        issues = self._grouped()
        cursor = clamp_cursor(self.cursor, len(issues))
        if issues:
            selected = issues[cursor]
        else:
            selected = None
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        id_width = _id_width(issues)
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
        title_start = len(head.plain)
        if selected:
            head.append(issue.title, style="bold")
        else:
            head.append(issue.title)
        head.stylize(MARQUEE_STYLE, title_start, title_start + len(issue.title))
        if selected:
            head = marquee_window(head, self._row_width(), self.marquee.offset)

        meta = Text(_META_INDENT)
        meta.append_text(_format_row_meta(issue))
        return truncating(head), truncating(meta)

    def selected_overflow(self) -> int:
        issues = self._grouped()
        if not issues:
            return 0
        cursor = clamp_cursor(self.cursor, len(issues))
        selected = issues[cursor]
        id_width = _id_width(issues)
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        head, _ = self._format_cell(selected, False, id_width, colors, accent)
        return marquee_overflow(head, self._row_width())

    def _row_width(self) -> int:
        return self.body_width() - CARD_CHROME

    def content_lines(self) -> list[str]:
        """render_view flattened to plain text, so the two cannot drift apart."""
        return plain_lines(self.render_view())

    def action_open_issue(self) -> None:
        issue = self.selected_item()
        if issue is None:
            return
        self.panel.open_issue(issue)

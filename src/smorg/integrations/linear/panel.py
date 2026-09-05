"""One list of your issues, grouped by status in actionability order."""

from __future__ import annotations

import io
import webbrowser

from rich.console import Console, Group, RenderableType
from rich.text import Text
from textual.binding import Binding

from smorg.core.contract import Item
from smorg.integrations.linear.palette import accent_for_background
from smorg.integrations.linear.source import Comment, Issue, IssueDetail
from smorg.shell.cards import CARD_TITLE_STYLE, CHANGED_MARK, SELECTED_MARK, format_card
from smorg.shell.detail_pane import SplitDetailPanel
from smorg.shell.format import age, format_hidden_line
from smorg.shell.markdown import Markdown
from smorg.shell.terminal_palette import StatusColors

# Ordered by actionability: doing, shepherding, queued, stuck.
_STATUS_RANKS = {"in progress": 0, "in review": 1, "todo": 3, "blocked": 5}

_DISC_IN_PROGRESS = "◐"
_DISC_IN_REVIEW = "◕"
_DISC_TODO = "○"
_DISC_BLOCKED = "⊘"

_PRIORITY_WIDTH = 3
# The meta line starts under the id column: marks (3), priority (3), and their two separators.
_META_INDENT = " " * 8


def _status_disc(status: str, status_type: str) -> str:
    normalized = status.casefold()
    if normalized == "in progress":
        return _DISC_IN_PROGRESS
    if normalized == "in review":
        return _DISC_IN_REVIEW
    if normalized == "todo":
        return _DISC_TODO
    if normalized == "blocked":
        return _DISC_BLOCKED
    # Unknown labels fall back to the stable machine category.
    if status_type == "started":
        return _DISC_IN_PROGRESS
    return _DISC_TODO


def _status_color(status: str, status_type: str, colors: StatusColors) -> str:
    normalized = status.casefold()
    if normalized == "in progress":
        return colors.yellow
    if normalized == "in review":
        return colors.green
    if normalized == "todo":
        return "dim"
    if normalized == "blocked":
        return colors.red
    if status_type == "started":
        return colors.yellow
    return "dim"


def _status_rank(status: str, status_type: str) -> int:
    known = _STATUS_RANKS.get(status.casefold())
    if known is not None:
        return known
    if status_type == "started":
        return 2
    return 4


def _format_priority(priority: str, colors: StatusColors, stage_color: str) -> Text:
    """Linear's priority icon: ascending bars filled to the level, dashes for none, [!] urgent."""
    if stage_color == "dim":
        # A dim fill would vanish against the dim unfilled bars, so a muted stage fills plain.
        fill = ""
    else:
        fill = stage_color
    if priority == "Urgent":
        return Text("[!]", style=f"bold {colors.red}")
    if priority == "High":
        return Text("▂▄▆", style=fill)
    if priority == "Medium":
        bars = Text("▂▄", style=fill)
        bars.append("▆", style="dim")
        return bars
    if priority == "Low":
        bars = Text("▂", style=fill)
        bars.append("▄▆", style="dim")
        return bars
    return Text("---", style="dim")


def _format_marks(selected: bool, changed: bool, accent: str) -> Text:
    marks = Text()
    if selected:
        marks.append(SELECTED_MARK, style="bold")
    else:
        marks.append(" ")
    marks.append(" ")
    if changed:
        marks.append(CHANGED_MARK, style=accent)
    else:
        marks.append(" ")
    return marks


def _format_card_title(status: str, status_type: str, count: int, colors: StatusColors) -> Text:
    color = _status_color(status, status_type, colors)
    if color == "dim":
        style = CARD_TITLE_STYLE
    else:
        style = f"{CARD_TITLE_STYLE} {color}"
    disc = _status_disc(status, status_type)
    return Text(f"{disc} {status} ({count})", style=style)


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


class LinearPanel(SplitDetailPanel):
    BINDINGS = [
        Binding("up", "cursor_up", "select issue", show=False),
        Binding("down", "cursor_down", "select issue", show=False),
        Binding("o", "open_selected", "open in Linear", show=False),
        Binding("enter", "toggle_detail", "view details", show=False),
        Binding("shift+up", "scroll_detail_up", "scroll details", show=False),
        Binding("shift+down", "scroll_detail_down", "scroll details", show=False),
    ]
    can_focus = True

    DEFAULT_CSS = """
    LinearPanel > #body { max-width: 120; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.cursor = 0

    def selected_item(self) -> Issue | None:
        issues = self._grouped()
        if not issues:
            return None
        return issues[self._clamped_cursor(len(issues))]

    def render_detail(self, item: Item, detail: object) -> RenderableType:
        if not isinstance(detail, IssueDetail):
            return super().render_detail(item, detail)
        # Markdown() interprets its input as CommonMark, not Rich's own "[style]" markup, so a
        # hostile "[red]x[/red]" body can't style or hide anything — only headings, emphasis,
        # code, and lists render as markdown.
        if detail.description:
            description = detail.description
        else:
            description = "no description"
        parts: list[RenderableType] = [
            self._format_detail_header(item, detail),
            Text(),
            Markdown(description),
        ]
        if detail.comments.hidden or detail.comments.hidden_is_lower_bound:
            parts.append(Text())
            parts.append(format_hidden_line(detail.comments, "comment"))
        for comment in detail.comments.items:
            parts.append(Text())
            parts.append(self._format_byline(comment))
            parts.append(Markdown(comment.body))
        return Group(*parts)

    def _format_detail_header(self, item: Item, detail: IssueDetail) -> Text:
        header = Text()
        header.append(item.id, style="dim")
        if isinstance(item, Issue):
            header.append(" · ")
            header.append(item.status)
        if detail.assignee:
            header.append(" · ")
            header.append(detail.assignee)
        return header

    def _format_byline(self, comment: Comment) -> Text:
        byline = Text(style="dim")
        if comment.author:
            author = comment.author
        else:
            author = "someone"
        byline.append(author)
        byline.append(" · ")
        byline.append(age(comment.created_at))
        return byline

    def selected_url(self) -> str | None:
        issue = self.selected_item()
        if issue is None:
            return None
        return issue.url

    def action_open_selected(self) -> None:
        issue = self.selected_item()
        if issue is None:
            return
        webbrowser.open(issue.url)
        self.mark_seen(issue)

    def action_toggle_detail(self) -> None:
        super().action_toggle_detail()
        issue = self.selected_item()
        if issue is not None and self.is_detail_showing(issue):
            self.mark_seen(issue)

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def _move(self, offset: int) -> None:
        issues = self._grouped()
        if not issues:
            return
        self.cursor = (self._clamped_cursor(len(issues)) + offset) % len(issues)
        self.refresh()

    def _clamped_cursor(self, count: int) -> int:
        if count == 0:
            return 0
        return min(self.cursor, count - 1)

    def _grouped(self) -> tuple[Issue, ...]:
        """Issues as one ordered sequence: status groups in fixed rank order, so a refresh never
        reshuffles them. The cursor moves through this same sequence.
        """
        groups: dict[str, list[Issue]] = {}
        for issue in self.items:
            if not isinstance(issue, Issue):
                continue
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

    def ready_text(self) -> str:
        console = Console(width=80, file=io.StringIO(), force_terminal=False)
        with console.capture() as capture:
            console.print(self.render_ready())
        return capture.get().strip()

    def render_ready(self) -> RenderableType:
        issues = self._grouped()
        cursor = self._clamped_cursor(len(issues))
        if issues:
            selected = issues[cursor]
        else:
            selected = None
        colors = self.status_colors()
        accent = accent_for_background(self._terminal_background())
        # One width for the whole list, so the title column never shifts at a group boundary.
        id_width = max((len(issue.id) for issue in issues), default=0)
        parts: list[RenderableType] = []
        for index, (status, status_type, members) in enumerate(_status_groups(issues)):
            if index > 0:
                parts.append(Text())
            title = _format_card_title(status, status_type, len(members), colors)
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
        changed = self.seen.is_changed(self.integration_id, issue)
        head.append_text(_format_marks(selected, changed, accent))
        head.append(" ")
        stage_color = _status_color(issue.status, issue.status_type, colors)
        priority = _format_priority(issue.priority, colors, stage_color)
        head.append_text(priority)
        head.append(" " * (_PRIORITY_WIDTH - len(priority.plain) + 1))
        head.append(issue.id.ljust(id_width), style="dim")
        head.append(" ")
        disc = _status_disc(issue.status, issue.status_type)
        head.append(disc, style=stage_color)
        head.append(" ")
        if selected:
            head.append(issue.title, style="bold")
        else:
            head.append(issue.title)
        head.no_wrap = True
        head.overflow = "ellipsis"

        meta = Text(_META_INDENT)
        meta.append_text(_format_row_meta(issue))
        meta.no_wrap = True
        meta.overflow = "ellipsis"
        return head, meta

"""The issue view: one issue's page, Linear's shape, opened from the list."""

from __future__ import annotations

import webbrowser
from datetime import date, datetime
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from smorg.auth.store import now
from smorg.core.contract import Newest
from smorg.integrations.linear.glyphs import format_priority, status_color, status_disc
from smorg.integrations.linear.navigation import (
    Target,
    Visit,
    format_target_row,
    format_trail,
    target_of_parent,
    target_of_sub_issue,
    targets_of,
)
from smorg.integrations.linear.source import (
    Comment,
    Issue,
    IssueDetail,
    RelatedIssue,
    Transition,
)
from smorg.integrations.linear.views.pickers import open_from_picker, trail_picker
from smorg.shell.cards import format_box, format_card, format_card_title
from smorg.shell.format import age, format_hidden_line, plain_lines, truncating
from smorg.shell.markdown import Markdown
from smorg.shell.panel import GutteredScroll, ViewBody
from smorg.shell.terminal_palette import StatusColors
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

_BACK_HINT_ROOT = "‹ esc — issues"
_BACK_HINT_GAP = 3
NARROW_BELOW = 90
SIDEBAR_WIDTH = 34
ACTIVITY_LIMIT = 8

_GLYPH_PROJECT = "▣"
_GLYPH_MILESTONE = "◇"
_GLYPH_ESTIMATE = "◭"
_GLYPH_DUE = "◷"
_GLYPH_ASSIGNEE = "@"
_GLYPH_LINK = "↗"
_GLYPH_LABEL = "●"
_GLYPH_RELATED = "◌"
_GLYPH_BLOCKED_BY = "⊘"
_SUBHEADING_STYLE = "dim"

_Event = Comment | Transition


def _format_header(
    issue: Issue, detail: IssueDetail | None, colors: StatusColors, accent: str
) -> list[RenderableType]:
    reference = Text(style="dim")
    reference.append(issue.id)
    team = issue.team
    if detail is not None and detail.team:
        team = detail.team
    if team:
        reference.append(f" · {team}")
    title = Text(issue.title, style="bold")
    lines: list[RenderableType] = [reference, title]
    if detail is not None and detail.parent is not None:
        target = target_of_parent(detail.parent)
        line = Text()
        line.append("Sub-issue of ", style="dim")
        line.append_text(format_target_row(target, colors, accent, False))
        lines.append(truncating(line))
    return lines


def _format_due(iso_date: str) -> str:
    """ "2026-09-30" -> "Sep 30" this year, "Jan 31, 2027" in any other."""
    due = date.fromisoformat(iso_date)
    month_day = f"{due.strftime('%b')} {due.day}"
    if due.year == now().year:
        return month_day
    return f"{month_day}, {due.year}"


def _format_row(glyph: str, glyph_style: str, value: str, value_style: str = "") -> Text:
    row = Text()
    row.append(glyph, style=glyph_style)
    row.append(" ")
    row.append(value, style=value_style)
    return truncating(row)


def _format_properties(
    issue: Issue, detail: IssueDetail | None, colors: StatusColors, accent: str
) -> list[Text]:
    status = issue.status
    status_type = issue.status_type
    priority = issue.priority
    if detail is not None:
        status = detail.status
        status_type = detail.status_type
        priority = detail.priority
    stage_color = status_color(status, status_type, colors, accent)
    disc = status_disc(status, status_type)
    if status:
        rows = [_format_row(disc, stage_color, status)]
    else:
        rows = [_format_row("◌", "dim", "loading…", "dim")]
    if priority and priority != "No priority":
        priority_row = format_priority(priority, colors, stage_color)
        priority_row.append(" ")
        priority_row.append(priority)
        rows.append(truncating(priority_row))
    if detail is None:
        return rows
    if detail.assignee:
        rows.append(_format_row(_GLYPH_ASSIGNEE, accent, detail.assignee))
    if detail.estimate:
        rows.append(_format_row(_GLYPH_ESTIMATE, accent, detail.estimate))
    if detail.due_date:
        rows.append(_format_row(_GLYPH_DUE, accent, _format_due(detail.due_date)))
    return rows


def _format_labels(detail: IssueDetail) -> list[Text]:
    rows: list[Text] = []
    for label in detail.labels:
        rows.append(_format_row(_GLYPH_LABEL, "dim", label))
    return rows


def _format_project(detail: IssueDetail, accent: str) -> list[Text]:
    rows = [_format_row(_GLYPH_PROJECT, accent, detail.project)]
    if detail.milestone:
        milestone = Text()
        milestone.append("└ ", style="dim")
        milestone.append(_GLYPH_MILESTONE, style=accent)
        milestone.append(" ")
        milestone.append(detail.milestone)
        rows.append(truncating(milestone))
    return rows


def _format_related_row(issue: RelatedIssue, glyph: str, glyph_style: str, prefix: str) -> Text:
    row = Text()
    if prefix:
        row.append(f"{prefix} ", style="dim")
    row.append(glyph, style=glyph_style)
    row.append(" ")
    if issue.url:
        row.append(issue.id, style=f"dim link {issue.url}")
    else:
        row.append(issue.id, style="dim")
    row.append(" ")
    row.append(issue.title)
    return truncating(row)


def _format_related(detail: IssueDetail, colors: StatusColors) -> list[Text]:
    rows: list[Text] = []
    for blocker in detail.blocked_by:
        rows.append(_format_related_row(blocker, _GLYPH_BLOCKED_BY, colors.red, ""))
    for blocked in detail.blocks:
        rows.append(_format_related_row(blocked, _GLYPH_RELATED, "dim", "blocks"))
    for related in detail.related:
        rows.append(_format_related_row(related, _GLYPH_RELATED, "dim", ""))
    return rows


def _format_links(detail: IssueDetail, accent: str) -> list[Text]:
    rows: list[Text] = []
    for link in detail.links:
        rows.append(_format_row(_GLYPH_LINK, accent, link.title, f"link {link.url}"))
    return rows


def _related_count(detail: IssueDetail) -> int:
    return len(detail.blocked_by) + len(detail.blocks) + len(detail.related)


def _format_sidebar_sections(
    issue: Issue, detail: IssueDetail | None, colors: StatusColors, accent: str
) -> list[tuple[str, list[Text]]]:
    """(heading, rows) pairs in Linear's order, only for sections with something to show."""
    sections = [("Properties", _format_properties(issue, detail, colors, accent))]
    if detail is None:
        return sections
    if detail.labels:
        sections.append(("Labels", _format_labels(detail)))
    if detail.project:
        sections.append(("Project", _format_project(detail, accent)))
    if _related_count(detail):
        sections.append(("Related", _format_related(detail, colors)))
    if detail.links:
        sections.append(("Links", _format_links(detail, accent)))
    return sections


def _format_description_card(detail: IssueDetail, accent: str) -> RenderableType:
    if detail.description:
        body: RenderableType = Markdown(detail.description)
    else:
        body = Text("no description", style="dim")
    title = format_card_title("description", accent)
    return format_card(title, [body])


def _format_sub_issues_card(
    detail: IssueDetail, colors: StatusColors, accent: str
) -> RenderableType:
    completed = [child for child in detail.sub_issues if child.status_type == "completed"]
    title = format_card_title(f"sub-issues ({len(completed)}/{len(detail.sub_issues)})", accent)
    rows: list[RenderableType] = []
    for child in detail.sub_issues:
        done = child.status_type == "completed"
        target = target_of_sub_issue(child)
        rows.append(format_target_row(target, colors, accent, done))
    return format_card(title, rows)


def _event_time(event: _Event) -> datetime:
    if isinstance(event, Comment):
        return event.created_at
    return event.at


def _activity_events(detail: IssueDetail) -> tuple[list[_Event], int, bool]:
    """The newest ACTIVITY_LIMIT events oldest-first, how many older ones exist, and whether
    that count is only a lower bound.
    """
    events: list[_Event] = [*detail.transitions, *detail.comments.items]
    ordered = sorted(events, key=_event_time)
    shown = ordered[-ACTIVITY_LIMIT:]
    dropped = len(ordered) - len(shown)
    hidden = dropped + detail.comments.hidden
    return shown, hidden, detail.comments.hidden_is_lower_bound


def _format_transition(
    step: Transition, is_creation: bool, creator: str, colors: StatusColors, accent: str
) -> Text:
    line = Text()
    disc = status_disc(step.status, step.status_type)
    line.append(disc, style=status_color(step.status, step.status_type, colors, accent))
    line.append(" ")
    if is_creation:
        line.append("created in ", style="dim")
    else:
        line.append("moved to ", style="dim")
    line.append(step.status, style="dim")
    if is_creation and creator:
        line.append(f" by {creator}", style="dim")
    line.append(f" · {age(step.at)}", style="dim")
    return line


def _format_comment(comment: Comment) -> list[RenderableType]:
    byline = Text(style="dim")
    if comment.author:
        byline.append(comment.author)
    else:
        byline.append("someone")
    byline.append(f" · {age(comment.created_at)}")
    parts: list[RenderableType] = [byline]
    if comment.body:
        parts.append(Markdown(comment.body))
    return parts


def _format_activity_card(detail: IssueDetail, colors: StatusColors, accent: str) -> RenderableType:
    shown, hidden, hidden_is_lower_bound = _activity_events(detail)
    body: list[RenderableType] = []
    if hidden or hidden_is_lower_bound:
        placeholder: Newest[_Event] = Newest(
            items=(), hidden=hidden, hidden_is_lower_bound=hidden_is_lower_bound
        )
        body.append(format_hidden_line(placeholder, "event"))
    creation = None
    if detail.transitions:
        creation = min(detail.transitions, key=lambda step: step.at)
    for event in shown:
        if body:
            body.append(Text())
        if isinstance(event, Transition):
            body.append(
                _format_transition(event, event is creation, detail.creator, colors, accent)
            )
        else:
            body.extend(_format_comment(event))
    title = format_card_title("activity", accent)
    return format_card(title, body)


def _join_inline(rows: list[Text]) -> Text:
    line = Text()
    for index, row in enumerate(rows):
        if index > 0:
            line.append(" · ", style="dim")
        row.no_wrap = False
        line.append_text(row)
    return line


def _format_compact_header(
    issue: Issue, detail: IssueDetail | None, colors: StatusColors, accent: str
) -> list[Text]:
    """The sidebar's properties, labels, and project as wrapping lines under the title."""
    lines = [_join_inline(_format_properties(issue, detail, colors, accent))]
    if detail is None:
        return lines
    if detail.labels:
        lines.append(_join_inline(_format_labels(detail)))
    if detail.project:
        project = Text()
        project.append(_GLYPH_PROJECT, style=accent)
        project.append(f" {detail.project}")
        if detail.milestone:
            project.append(" › ", style="dim")
            project.append(_GLYPH_MILESTONE, style=accent)
            project.append(f" {detail.milestone}")
        lines.append(project)
    return lines


def _format_trailing_cards(
    detail: IssueDetail, colors: StatusColors, accent: str
) -> list[RenderableType]:
    cards: list[RenderableType] = []
    count = _related_count(detail)
    if count:
        related_rows = _format_related(detail, colors)
        title = format_card_title(f"related ({count})", accent)
        cards.append(format_card(title, list(related_rows)))
    if detail.links:
        title = format_card_title(f"links ({len(detail.links)})", accent)
        cards.append(format_card(title, list(_format_links(detail, accent))))
    return cards


class LinearIssueView(Horizontal, HostedView):
    BINDINGS = [
        Binding("enter", "open_from_here", "open from here", show=False),
        Binding("backspace", "show_trail", "back to…", show=False),
        Binding("o", "open_in_linear", "open in Linear", show=False),
        Binding("escape", "back", "back", show=False),
    ]

    DEFAULT_CSS = f"""
    LinearIssueView {{ max-width: 120; }}
    LinearIssueView > #reading {{ width: 1fr; }}
    LinearIssueView > #sidebar {{ dock: right; width: {SIDEBAR_WIDTH}; }}
    LinearIssueView #reading-body {{ height: auto; }}
    LinearIssueView #sidebar-body {{ height: auto; }}
    """

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__()
        self.panel = panel
        self.narrow = False
        self.picker_cursor = 0

    def compose(self) -> ComposeResult:
        reading = GutteredScroll(ViewBody(self._render_reading, id="reading-body"), id="reading")
        reading.can_focus = True
        yield reading
        sidebar = GutteredScroll(ViewBody(self._render_sidebar, id="sidebar-body"), id="sidebar")
        sidebar.can_focus = False
        yield sidebar

    def _render_reading(self) -> RenderableType:
        issue = self.panel.viewed
        if issue is None:
            return Text()
        return self.render_reading(issue, self.detail(), self.narrow)

    def _render_sidebar(self) -> RenderableType:
        issue = self.panel.viewed
        if issue is None:
            return Text()
        return self.render_sidebar(issue, self.detail())

    def on_mount(self) -> None:
        self._sync_columns()

    def on_resize(self, event: events.Resize) -> None:
        self._sync_columns()

    def focus(self, scroll_visible: bool = True):
        self.query_one("#reading", VerticalScroll).focus(scroll_visible)
        return self

    def detail(self) -> IssueDetail | None:
        issue = self.panel.viewed
        if issue is None:
            return None
        raw = self.panel.detail_for(issue)
        if isinstance(raw, IssueDetail):
            return raw
        return None

    def reading_scroll_y(self) -> int:
        if not self.is_mounted:
            return 0
        return int(self.query_one("#reading", VerticalScroll).scroll_offset.y)

    def restore_view_state(self, visit: Visit) -> None:
        self.picker_cursor = visit.picker_cursor
        if not self.is_mounted:
            return
        reading = self.query_one("#reading", VerticalScroll)
        reading.scroll_to(y=visit.scroll_y, animate=False)

    def _back_hint(self) -> str:
        ids = self.panel.trail_ids()
        if len(ids) < 2:
            return _BACK_HINT_ROOT
        return f"‹ esc — {ids[-2]}"

    def _budget(self) -> int:
        if not self.is_mounted:
            return 80
        body = self.query_one("#reading-body", Static)
        if body.size.width > 0:
            return body.size.width
        return 80

    def _sync_columns(self) -> None:
        if not self.is_mounted:
            return
        self.narrow = self.size.width < NARROW_BELOW
        self.query_one("#sidebar", VerticalScroll).display = not self.narrow
        self.refresh_content()

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#reading-body", Static).refresh(layout=True)
        self.query_one("#sidebar-body", Static).refresh(layout=True)

    def render_reading(
        self, issue: Issue, detail: IssueDetail | None, narrow: bool
    ) -> RenderableType:
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        parts: list[RenderableType] = [*self._format_trail_lines(narrow), Text()]
        parts.extend(_format_header(issue, detail, colors, accent))
        if narrow:
            parts.extend(_format_compact_header(issue, detail, colors, accent))
        parts.append(Text())
        error = self.panel.detail_error_for(issue)
        if detail is None and error is not None:
            parts.append(Text(f"could not load: {error}"))
            return Group(*parts)
        if detail is None:
            parts.append(Text("loading…", style="dim"))
            return Group(*parts)
        parts.append(_format_description_card(detail, accent))
        if detail.sub_issues:
            parts.append(Text())
            parts.append(_format_sub_issues_card(detail, colors, accent))
        shown, hidden, hidden_is_lower_bound = _activity_events(detail)
        if shown or hidden or hidden_is_lower_bound:
            parts.append(Text())
            parts.append(_format_activity_card(detail, colors, accent))
        if narrow:
            for card in _format_trailing_cards(detail, colors, accent):
                parts.append(Text())
                parts.append(card)
        return Group(*parts)

    def _format_trail_lines(self, narrow: bool) -> list[RenderableType]:
        hint = Text(self._back_hint(), style="dim")
        ids = self.panel.trail_ids()
        if narrow:
            trail = format_trail(ids, self._budget())
            return [hint, trail]
        budget = self._budget() - hint.cell_len - _BACK_HINT_GAP
        trail = format_trail(ids, budget)
        line = Table.grid(expand=True)
        line.add_column(no_wrap=True)
        line.add_column(justify="right", no_wrap=True, overflow="ellipsis")
        line.add_row(hint, trail)
        return [line]

    def render_sidebar(self, issue: Issue, detail: IssueDetail | None) -> RenderableType:
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        body: list[RenderableType] = []
        for heading, rows in _format_sidebar_sections(issue, detail, colors, accent):
            if body:
                body.append(Text())
            body.append(Text(heading, style=_SUBHEADING_STYLE))
            body.extend(rows)
        return format_box(body)

    def content_lines(self) -> list[str]:
        """render_reading and render_sidebar flattened to plain text, reading column first."""
        issue = self.panel.viewed
        if issue is None:
            return []
        budget = self._budget()
        lines = plain_lines(self.render_reading(issue, self.detail(), self.narrow), budget)
        if not self.narrow:
            lines.extend(plain_lines(self.render_sidebar(issue, self.detail()), budget))
        return lines

    def action_open_in_linear(self) -> None:
        issue = self.panel.viewed
        if issue is None:
            return
        webbrowser.open(issue.url)

    def action_open_from_here(self) -> None:
        issue = self.panel.viewed
        if issue is None:
            return
        detail = self.detail()
        if detail is None:
            if self.panel.detail_error_for(issue) is not None:
                self.panel.notify("could not load")
            else:
                self.panel.notify("still loading")
            return
        sections = targets_of(detail)
        if not sections:
            self.panel.notify("nothing to open from here")
            return
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        picker = open_from_picker(issue.id, sections, colors, accent, self.picker_cursor)

        def picked(value: object | None) -> None:
            self.picker_cursor = picker.cursor
            if isinstance(value, Target):
                self.panel.open_target(value)

        self.app.push_screen(picker, picked)

    def action_show_trail(self) -> None:
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        picker = trail_picker(self.panel.trail.visits, colors, accent)
        self.app.push_screen(picker, self._trail_picked)

    def _trail_picked(self, value: object | None) -> None:
        if not isinstance(value, int):
            return
        last = len(self.panel.trail.visits) - 1
        if value == last:
            return
        self.panel.go_back_to(value)

    def action_back(self) -> None:
        self.panel.go_back()

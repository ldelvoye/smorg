"""The issue view: one issue's page, Linear's shape, opened from the list."""

from __future__ import annotations

import io
import webbrowser
from datetime import date, datetime
from typing import TYPE_CHECKING

from rich.console import Console, Group, RenderableType
from rich.text import Text
from textual import events
from textual.app import ComposeResult, RenderResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from smorg.auth.store import now
from smorg.core.contract import Newest
from smorg.integrations.linear.glyphs import format_priority, status_color, status_disc
from smorg.integrations.linear.palette import accent_for_background
from smorg.integrations.linear.source import (
    Comment,
    Issue,
    IssueDetail,
    RelatedIssue,
    SubIssue,
    Transition,
)
from smorg.shell.cards import CARD_TITLE_STYLE, format_box, format_card
from smorg.shell.format import age, format_hidden_line
from smorg.shell.markdown import Markdown
from smorg.shell.panel import ScrollGutter
from smorg.shell.terminal_palette import StatusColors

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

_BACK_HINT = "‹ esc — issues"
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
    issue: Issue, detail: IssueDetail | None, colors: StatusColors
) -> list[RenderableType]:
    reference = Text(style="dim")
    reference.append(issue.id)
    if issue.team:
        reference.append(f" · {issue.team}")
    title = Text(issue.title, style="bold")
    lines: list[RenderableType] = [reference, title]
    if detail is not None and detail.parent is not None:
        parent = detail.parent
        line = Text()
        line.append("Sub-issue of ", style="dim")
        disc = status_disc(parent.status, parent.status_type)
        line.append(disc, style=status_color(parent.status, parent.status_type, colors))
        line.append(" ")
        line.append(parent.id, style="dim")
        line.append(" ")
        line.append(parent.title)
        lines.append(_truncating(line))
    return lines


def _truncating(text: Text) -> Text:
    text.no_wrap = True
    text.overflow = "ellipsis"
    return text


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
    return _truncating(row)


def _format_properties(
    issue: Issue, detail: IssueDetail | None, colors: StatusColors, accent: str
) -> list[Text]:
    stage_color = status_color(issue.status, issue.status_type, colors)
    disc = status_disc(issue.status, issue.status_type)
    rows = [_format_row(disc, stage_color, issue.status)]
    if issue.priority and issue.priority != "No priority":
        priority = format_priority(issue.priority, colors, stage_color)
        priority.append(" ")
        priority.append(issue.priority)
        rows.append(_truncating(priority))
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
        rows.append(_truncating(milestone))
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
    return _truncating(row)


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
    return format_card(Text("description", style=f"{CARD_TITLE_STYLE} {accent}"), [body])


def _format_sub_issue_row(child: SubIssue, colors: StatusColors) -> Text:
    done = child.status_type == "completed"
    row = Text()
    disc = status_disc(child.status, child.status_type)
    row.append(disc, style=status_color(child.status, child.status_type, colors))
    row.append(" ")
    if child.url:
        row.append(child.id, style=f"dim link {child.url}")
    else:
        row.append(child.id, style="dim")
    row.append("  ")
    row.append(child.title)
    if done:
        row.stylize("dim")
    return _truncating(row)


def _format_sub_issues_card(
    detail: IssueDetail, colors: StatusColors, accent: str
) -> RenderableType:
    done = [child for child in detail.sub_issues if child.status_type == "completed"]
    title = Text(
        f"sub-issues ({len(done)}/{len(detail.sub_issues)})", style=f"{CARD_TITLE_STYLE} {accent}"
    )
    rows: list[RenderableType] = []
    for child in detail.sub_issues:
        rows.append(_format_sub_issue_row(child, colors))
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
    step: Transition, is_creation: bool, creator: str, colors: StatusColors
) -> Text:
    line = Text()
    disc = status_disc(step.status, step.status_type)
    line.append(disc, style=status_color(step.status, step.status_type, colors))
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
            body.append(_format_transition(event, event is creation, detail.creator, colors))
        else:
            body.extend(_format_comment(event))
    return format_card(Text("activity", style=f"{CARD_TITLE_STYLE} {accent}"), body)


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
    if _related_count(detail):
        related_rows = _format_related(detail, colors)
        count = _related_count(detail)
        title = Text(f"related ({count})", style=f"{CARD_TITLE_STYLE} {accent}")
        cards.append(format_card(title, list(related_rows)))
    if detail.links:
        title = Text(f"links ({len(detail.links)})", style=f"{CARD_TITLE_STYLE} {accent}")
        cards.append(format_card(title, list(_format_links(detail, accent))))
    return cards


class _ReadingBody(Static):
    """Draws the reading column; owns no state of its own."""

    DEFAULT_CSS = """
    _ReadingBody { height: auto; }
    """

    def __init__(self, view: LinearIssueView) -> None:
        # markup off: titles and bodies carry server-controlled text, so a hostile value
        # can't style, hide, or garble the view via Rich markup.
        super().__init__(markup=False, id="reading-body")
        self._view = view

    def render(self) -> RenderResult:
        issue = self._view.panel.viewed
        if issue is None:
            return Text()
        return self._view.render_reading(issue, self._view.detail(), self._view.narrow)


class _SidebarBody(Static):
    """Draws the properties column; owns no state of its own."""

    DEFAULT_CSS = """
    _SidebarBody { height: auto; }
    """

    def __init__(self, view: LinearIssueView) -> None:
        super().__init__(markup=False, id="sidebar-body")
        self._view = view

    def render(self) -> RenderResult:
        issue = self._view.panel.viewed
        if issue is None:
            return Text()
        return self._view.render_sidebar(issue, self._view.detail())


class LinearIssueView(Horizontal):
    BINDINGS = [
        Binding("o", "open_in_linear", "open in Linear", show=False),
        Binding("escape", "back_to_issues", "back to issues", show=False),
    ]

    DEFAULT_CSS = f"""
    LinearIssueView {{ max-width: 120; }}
    LinearIssueView > #reading {{ width: 1fr; scrollbar-size-vertical: 0; }}
    LinearIssueView > #sidebar {{
        dock: right; width: {SIDEBAR_WIDTH}; scrollbar-size-vertical: 0;
    }}
    """

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__()
        self.panel = panel
        self.narrow = False

    def compose(self) -> ComposeResult:
        reading = VerticalScroll(_ReadingBody(self), ScrollGutter(), id="reading")
        reading.can_focus = True
        yield reading
        sidebar = VerticalScroll(_SidebarBody(self), id="sidebar")
        sidebar.can_focus = False
        yield sidebar

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

    def _sync_columns(self) -> None:
        if not self.is_mounted:
            return
        self.narrow = self.size.width < NARROW_BELOW
        self.query_one("#sidebar", VerticalScroll).display = not self.narrow
        self.refresh_content()

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        self.query_one(_ReadingBody).refresh(layout=True)
        self.query_one(_SidebarBody).refresh(layout=True)

    def render_reading(
        self, issue: Issue, detail: IssueDetail | None, narrow: bool
    ) -> RenderableType:
        colors = self.panel.status_colors()
        accent = accent_for_background(self.panel._terminal_background())
        parts: list[RenderableType] = [Text(_BACK_HINT, style="dim"), Text()]
        parts.extend(_format_header(issue, detail, colors))
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

    def render_sidebar(self, issue: Issue, detail: IssueDetail | None) -> RenderableType:
        colors = self.panel.status_colors()
        accent = accent_for_background(self.panel._terminal_background())
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
        console = Console(width=80, file=io.StringIO(), force_terminal=False)
        with console.capture() as capture:
            console.print(self.render_reading(issue, self.detail(), self.narrow))
            if not self.narrow:
                console.print(self.render_sidebar(issue, self.detail()))
        return capture.get().splitlines()

    def action_open_in_linear(self) -> None:
        issue = self.panel.viewed
        if issue is None:
            return
        webbrowser.open(issue.url)

    def action_back_to_issues(self) -> None:
        self.panel.close_issue()

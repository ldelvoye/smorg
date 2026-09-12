"""The issue view: one issue's page, Linear's shape, opened from the list."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.binding import Binding

from smorg.core.contract import Newest
from smorg.integrations.linear.dates import target_label
from smorg.integrations.linear.glyphs import format_priority, status_color, status_disc
from smorg.integrations.linear.navigation import (
    Target,
    Visit,
    format_target_row,
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
from smorg.integrations.linear.views.page import SUBHEADING_STYLE, LinearPage
from smorg.integrations.linear.views.pickers import open_from_picker
from smorg.integrations.linear.views.properties import (
    GLYPH_ASSIGNEE,
    GLYPH_DUE,
    GLYPH_LINK,
    format_property_row,
    join_inline,
)
from smorg.shell.cards import format_box, format_card, format_card_title
from smorg.shell.format import age, format_hidden_line, truncating
from smorg.shell.markdown import Markdown
from smorg.shell.terminal_palette import StatusColors

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

ACTIVITY_LIMIT = 8

_GLYPH_PROJECT = "▣"
_GLYPH_MILESTONE = "◇"
_GLYPH_ESTIMATE = "◭"
_GLYPH_LABEL = "●"
_GLYPH_RELATED = "◌"
_GLYPH_BLOCKED_BY = "⊘"

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
    return target_label(iso_date, "day")


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
        rows = [format_property_row(disc, stage_color, status)]
    else:
        rows = [format_property_row("◌", "dim", "loading…", "dim")]
    if priority and priority != "No priority":
        priority_row = format_priority(priority, colors, stage_color)
        priority_row.append(" ")
        priority_row.append(priority)
        rows.append(truncating(priority_row))
    if detail is None:
        return rows
    if detail.assignee:
        rows.append(format_property_row(GLYPH_ASSIGNEE, accent, detail.assignee))
    if detail.estimate:
        rows.append(format_property_row(_GLYPH_ESTIMATE, accent, detail.estimate))
    if detail.due_date:
        rows.append(format_property_row(GLYPH_DUE, accent, _format_due(detail.due_date)))
    return rows


def _format_labels(detail: IssueDetail) -> list[Text]:
    rows: list[Text] = []
    for label in detail.labels:
        rows.append(format_property_row(_GLYPH_LABEL, "dim", label))
    return rows


def _format_project(detail: IssueDetail, accent: str) -> list[Text]:
    rows = [format_property_row(_GLYPH_PROJECT, accent, detail.project)]
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
        rows.append(format_property_row(GLYPH_LINK, accent, link.title, f"link {link.url}"))
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


def _format_compact_header(
    issue: Issue, detail: IssueDetail | None, colors: StatusColors, accent: str
) -> list[Text]:
    """The sidebar's properties, labels, and project as wrapping lines under the title."""
    lines = [join_inline(_format_properties(issue, detail, colors, accent))]
    if detail is None:
        return lines
    if detail.labels:
        lines.append(join_inline(_format_labels(detail)))
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


class LinearIssueView(LinearPage):
    BINDINGS = [
        Binding("enter", "open_from_here", "open from here", show=False),
        *LinearPage.BINDINGS,
    ]

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__(panel)
        self.picker_cursor = 0

    def page_item(self) -> Issue | None:
        return self.panel.viewed

    def detail(self) -> IssueDetail | None:
        issue = self.page_item()
        if issue is None:
            return None
        raw = self.panel.detail_for(issue)
        if isinstance(raw, IssueDetail):
            return raw
        return None

    def restore_view_state(self, visit: Visit) -> None:
        self.picker_cursor = visit.picker_cursor
        super().restore_view_state(visit)

    def render_reading(self, narrow: bool) -> RenderableType:
        issue = self.page_item()
        if issue is None:
            return Text()
        detail = self.detail()
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

    def render_sidebar(self) -> RenderableType:
        issue = self.page_item()
        if issue is None:
            return Text()
        detail = self.detail()
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        body: list[RenderableType] = []
        for heading, rows in _format_sidebar_sections(issue, detail, colors, accent):
            if body:
                body.append(Text())
            body.append(Text(heading, style=SUBHEADING_STYLE))
            body.extend(rows)
        return format_box(body)

    def action_open_from_here(self) -> None:
        issue = self.page_item()
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

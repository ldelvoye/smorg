"""The project page: its description, properties, milestones, and a summary of its issues."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from smorg.integrations.linear.dates import target_label
from smorg.integrations.linear.glyphs import format_priority, status_color, status_disc
from smorg.integrations.linear.navigation import Visit, format_trail
from smorg.integrations.linear.source import Project, ProjectDetail
from smorg.integrations.linear.views import LinearView
from smorg.integrations.linear.views.issue import (
    _BACK_HINT_GAP,
    _BACK_HINT_PREFIX,
    _GLYPH_ASSIGNEE,
    _GLYPH_DUE,
    _GLYPH_LINK,
    _SUBHEADING_STYLE,
    NARROW_BELOW,
    SIDEBAR_WIDTH,
    _format_row,
    _join_inline,
)
from smorg.integrations.linear.views.pickers import trail_picker
from smorg.integrations.linear.views.project_issues import _format_issue_counts, _status_tallies
from smorg.integrations.linear.views.projects import _format_milestone_row
from smorg.shell.cards import format_box, format_card, format_card_title
from smorg.shell.format import plain_lines, truncating
from smorg.shell.markdown import Markdown
from smorg.shell.panel import GutteredScroll, ViewBody
from smorg.shell.terminal_palette import StatusColors
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

_GLYPH_INITIATIVE = "◈"
_GLYPH_TEAM = "●"


def _format_issues_summary_card(
    detail: ProjectDetail, colors: StatusColors, accent: str
) -> RenderableType:
    title = format_card_title(f"issues ({len(detail.issues)})", accent)
    if not detail.issues:
        return format_card(title, [Text("no issues", style="dim")])
    tallies = _status_tallies(detail.issues)
    counts = _format_issue_counts(tallies, colors, accent)
    body: list[RenderableType] = [counts, Text(), Text("⏎ to open", style="dim")]
    return format_card(title, body)


def _format_header(project: Project) -> list[RenderableType]:
    lines: list[RenderableType] = [Text(project.name, style="bold")]
    if project.summary:
        lines.append(Text(project.summary, style="dim"))
    return lines


def _format_properties(project: Project, colors: StatusColors, accent: str) -> list[Text]:
    stage_color = status_color(project.status, project.status_type, colors, accent)
    disc = status_disc(project.status, project.status_type)
    rows = [_format_row(disc, stage_color, project.status)]
    if project.priority and project.priority != "No priority":
        priority_row = format_priority(project.priority, colors, stage_color)
        priority_row.append(" ")
        priority_row.append(project.priority)
        rows.append(truncating(priority_row))
    if project.lead:
        rows.append(_format_row(_GLYPH_ASSIGNEE, accent, project.lead))
    start = target_label(project.start_date, "day")
    target = target_label(project.target_date, project.target_resolution)
    dates = ""
    if start and target:
        dates = f"{start} → {target}"
    elif start:
        dates = f"from {start}"
    elif target:
        dates = f"due {target}"
    if dates:
        rows.append(_format_row(_GLYPH_DUE, accent, dates))
    segments = project.url.rsplit("/", 1)
    slug = segments[-1]
    if slug:
        rows.append(_format_row(_GLYPH_LINK, accent, slug, f"link {project.url}"))
    return rows


def _format_initiatives(detail: ProjectDetail, accent: str) -> list[Text]:
    rows: list[Text] = []
    for initiative in detail.initiatives:
        rows.append(_format_row(_GLYPH_INITIATIVE, accent, initiative))
    return rows


def _format_teams(project: Project) -> list[Text]:
    rows: list[Text] = []
    for team in project.teams:
        rows.append(_format_row(_GLYPH_TEAM, "dim", team))
    return rows


def _format_sidebar_sections(
    project: Project, detail: ProjectDetail | None, colors: StatusColors, accent: str
) -> list[tuple[str, list[Text]]]:
    sections = [("Properties", _format_properties(project, colors, accent))]
    if detail is not None and detail.initiatives:
        sections.append(("Initiatives", _format_initiatives(detail, accent)))
    if project.teams:
        sections.append(("Teams", _format_teams(project)))
    return sections


def _format_compact_header(project: Project, colors: StatusColors, accent: str) -> Text:
    rows = _format_properties(project, colors, accent)
    return _join_inline(rows)


def _format_description_card(detail: ProjectDetail, accent: str) -> RenderableType:
    if detail.description:
        body: RenderableType = Markdown(detail.description)
    else:
        body = Text("no description", style="dim")
    title = format_card_title("description", accent)
    return format_card(title, [body])


def _format_milestones_card(detail: ProjectDetail, accent: str) -> RenderableType:
    title = format_card_title(f"milestones ({len(detail.milestones)})", accent)
    if not detail.milestones:
        return format_card(title, [Text("no milestones", style="dim")])
    body: list[RenderableType] = []
    for milestone in detail.milestones:
        body.append(_format_milestone_row(milestone, accent))
    return format_card(title, body)


def _format_trailing_cards(
    project: Project, detail: ProjectDetail, accent: str
) -> list[RenderableType]:
    cards: list[RenderableType] = []
    if detail.initiatives:
        title = format_card_title(f"initiatives ({len(detail.initiatives)})", accent)
        rows = _format_initiatives(detail, accent)
        cards.append(format_card(title, list(rows)))
    if project.teams:
        title = format_card_title(f"teams ({len(project.teams)})", accent)
        team_rows = _format_teams(project)
        cards.append(format_card(title, list(team_rows)))
    return cards


class LinearProjectView(Horizontal, HostedView):
    BINDINGS = [
        Binding("enter", "open_issues", "view issues", show=False),
        Binding("backspace", "show_trail", "back to…", show=False),
        Binding("o", "open_in_linear", "open in Linear", show=False),
        Binding("escape", "back", "back", show=False),
    ]

    DEFAULT_CSS = f"""
    LinearProjectView {{ max-width: 120; }}
    LinearProjectView > #project-reading {{ width: 1fr; }}
    LinearProjectView > #project-sidebar {{ dock: right; width: {SIDEBAR_WIDTH}; }}
    LinearProjectView #project-reading-body {{ height: auto; }}
    LinearProjectView #project-sidebar-body {{ height: auto; }}
    """

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__()
        self.panel = panel
        self.narrow = False

    def compose(self) -> ComposeResult:
        body = ViewBody(self._render_reading, id="project-reading-body")
        reading = GutteredScroll(body, id="project-reading")
        reading.can_focus = True
        yield reading
        sidebar_body = ViewBody(self._render_sidebar, id="project-sidebar-body")
        sidebar = GutteredScroll(sidebar_body, id="project-sidebar")
        sidebar.can_focus = False
        yield sidebar

    def _render_reading(self) -> RenderableType:
        project = self.panel.viewed_project
        if project is None:
            return Text()
        return self.render_reading(project, self.detail(), self.narrow)

    def _render_sidebar(self) -> RenderableType:
        project = self.panel.viewed_project
        if project is None:
            return Text()
        return self.render_sidebar(project, self.detail())

    def on_mount(self) -> None:
        self._sync_columns()

    def on_resize(self, event: events.Resize) -> None:
        self._sync_columns()

    def focus(self, scroll_visible: bool = True):
        self.query_one("#project-reading", VerticalScroll).focus(scroll_visible)
        return self

    def detail(self) -> ProjectDetail | None:
        project = self.panel.viewed_project
        if project is None:
            return None
        raw = self.panel.detail_for(project)
        if isinstance(raw, ProjectDetail):
            return raw
        return None

    def reading_scroll_y(self) -> int:
        if not self.is_mounted:
            return 0
        return int(self.query_one("#project-reading", VerticalScroll).scroll_offset.y)

    def restore_view_state(self, visit: Visit) -> None:
        if not self.is_mounted:
            return
        reading = self.query_one("#project-reading", VerticalScroll)
        reading.scroll_to(y=visit.scroll_y, animate=False)

    def _back_hint(self) -> str:
        labels = self.panel.trail_labels()
        if len(labels) < 2:
            root_label = str(self.panel.trail.root)
            return f"{_BACK_HINT_PREFIX}{root_label}"
        return f"{_BACK_HINT_PREFIX}{labels[-2]}"

    def _budget(self) -> int:
        if not self.is_mounted:
            return 80
        body = self.query_one("#project-reading-body", Static)
        if body.size.width > 0:
            return body.size.width
        return 80

    def _sync_columns(self) -> None:
        if not self.is_mounted:
            return
        self.narrow = self.size.width < NARROW_BELOW
        self.query_one("#project-sidebar", VerticalScroll).display = not self.narrow
        self.refresh_content()

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#project-reading-body", Static).refresh(layout=True)
        self.query_one("#project-sidebar-body", Static).refresh(layout=True)

    def render_reading(
        self, project: Project, detail: ProjectDetail | None, narrow: bool
    ) -> RenderableType:
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        parts: list[RenderableType] = [*self._format_trail_lines(narrow), Text()]
        parts.extend(_format_header(project))
        if narrow:
            parts.append(_format_compact_header(project, colors, accent))
        parts.append(Text())
        error = self.panel.detail_error_for(project)
        if detail is None and error is not None:
            parts.append(Text(f"could not load: {error}"))
            return Group(*parts)
        if detail is None:
            parts.append(Text("loading…", style="dim"))
            return Group(*parts)
        parts.append(_format_description_card(detail, accent))
        parts.append(Text())
        parts.append(_format_milestones_card(detail, accent))
        parts.append(Text())
        parts.append(_format_issues_summary_card(detail, colors, accent))
        if narrow:
            for card in _format_trailing_cards(project, detail, accent):
                parts.append(Text())
                parts.append(card)
        return Group(*parts)

    def _format_trail_lines(self, narrow: bool) -> list[RenderableType]:
        hint = Text(self._back_hint(), style="dim")
        labels = self.panel.trail_labels()
        root_label = str(self.panel.trail.root)
        if narrow:
            trail = format_trail(labels, self._budget(), root_label)
            return [hint, trail]
        budget = self._budget() - hint.cell_len - _BACK_HINT_GAP
        trail = format_trail(labels, budget, root_label)
        line = Table.grid(expand=True)
        line.add_column(no_wrap=True)
        line.add_column(justify="right", no_wrap=True, overflow="ellipsis")
        line.add_row(hint, trail)
        return [line]

    def render_sidebar(self, project: Project, detail: ProjectDetail | None) -> RenderableType:
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        body: list[RenderableType] = []
        for heading, rows in _format_sidebar_sections(project, detail, colors, accent):
            if body:
                body.append(Text())
            body.append(Text(heading, style=_SUBHEADING_STYLE))
            body.extend(rows)
        return format_box(body)

    def content_lines(self) -> list[str]:
        project = self.panel.viewed_project
        if project is None:
            return []
        budget = self._budget()
        lines = plain_lines(self.render_reading(project, self.detail(), self.narrow), budget)
        if not self.narrow:
            lines.extend(plain_lines(self.render_sidebar(project, self.detail()), budget))
        return lines

    def action_open_in_linear(self) -> None:
        project = self.panel.viewed_project
        if project is None:
            return
        webbrowser.open(project.url)

    def action_open_issues(self) -> None:
        self.panel.show_view(LinearView.PROJECT_ISSUES)

    def action_show_trail(self) -> None:
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        root_label = str(self.panel.trail.root)
        picker = trail_picker(self.panel.trail.visits, root_label, colors, accent)
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

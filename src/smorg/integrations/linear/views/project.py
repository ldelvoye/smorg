"""The project page: its description, properties, milestones, and a summary of its issues."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text
from textual.binding import Binding

from smorg.integrations.linear.dates import target_label
from smorg.integrations.linear.glyphs import format_priority, project_glyph, status_color
from smorg.integrations.linear.source import Project, ProjectDetail
from smorg.integrations.linear.views import LinearView
from smorg.integrations.linear.views.page import SUBHEADING_STYLE, LinearPage
from smorg.integrations.linear.views.project_issues import format_issue_counts, status_tallies
from smorg.integrations.linear.views.projects import format_milestone_row
from smorg.integrations.linear.views.properties import (
    GLYPH_ASSIGNEE,
    GLYPH_DUE,
    GLYPH_LINK,
    format_property_row,
    join_inline,
)
from smorg.shell.cards import format_box, format_card, format_card_title
from smorg.shell.format import truncating
from smorg.shell.markdown import Markdown
from smorg.shell.terminal_palette import StatusColors

_GLYPH_INITIATIVE = "◈"
_GLYPH_TEAM = "●"


def _format_issues_summary_card(
    detail: ProjectDetail, colors: StatusColors, accent: str
) -> RenderableType:
    title = format_card_title(f"issues ({len(detail.issues)})", accent)
    if not detail.issues:
        return format_card(title, [Text("no issues", style="dim")])
    tallies = status_tallies(detail.issues)
    counts = format_issue_counts(tallies, colors, accent)
    body: list[RenderableType] = [counts, Text(), Text("⏎ to open", style="dim")]
    return format_card(title, body)


def _format_header(project: Project) -> list[RenderableType]:
    lines: list[RenderableType] = [Text(project.name, style="bold")]
    if project.summary:
        lines.append(Text(project.summary, style="dim"))
    return lines


def _format_properties(project: Project, colors: StatusColors, accent: str) -> list[Text]:
    stage_color = status_color(project.status, project.status_type, colors, accent)
    glyph = project_glyph(project.status_type)
    rows = [format_property_row(glyph, stage_color, project.status)]
    if project.priority and project.priority != "No priority":
        priority_row = format_priority(project.priority, colors, stage_color)
        priority_row.append(" ")
        priority_row.append(project.priority)
        rows.append(truncating(priority_row))
    if project.lead:
        rows.append(format_property_row(GLYPH_ASSIGNEE, accent, project.lead))
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
        rows.append(format_property_row(GLYPH_DUE, accent, dates))
    segments = project.url.rsplit("/", 1)
    slug = segments[-1]
    if slug:
        rows.append(format_property_row(GLYPH_LINK, accent, slug, f"link {project.url}"))
    return rows


def _format_initiatives(detail: ProjectDetail, accent: str) -> list[Text]:
    rows: list[Text] = []
    for initiative in detail.initiatives:
        rows.append(format_property_row(_GLYPH_INITIATIVE, accent, initiative))
    return rows


def _format_teams(project: Project) -> list[Text]:
    rows: list[Text] = []
    for team in project.teams:
        rows.append(format_property_row(_GLYPH_TEAM, "dim", team))
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
    return join_inline(rows)


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
        body.append(format_milestone_row(milestone, accent))
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


class LinearProjectView(LinearPage):
    BINDINGS = [
        Binding("enter", "open_issues", "view issues", show=False),
        *LinearPage.BINDINGS,
    ]

    def page_item(self) -> Project | None:
        return self.panel.viewed_project

    def detail(self) -> ProjectDetail | None:
        project = self.page_item()
        if project is None:
            return None
        raw = self.panel.detail_for(project)
        if isinstance(raw, ProjectDetail):
            return raw
        return None

    def render_reading(self, narrow: bool) -> RenderableType:
        project = self.page_item()
        if project is None:
            return Text()
        detail = self.detail()
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

    def render_sidebar(self) -> RenderableType:
        project = self.page_item()
        if project is None:
            return Text()
        detail = self.detail()
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        body: list[RenderableType] = []
        for heading, rows in _format_sidebar_sections(project, detail, colors, accent):
            if body:
                body.append(Text())
            body.append(Text(heading, style=SUBHEADING_STYLE))
            body.extend(rows)
        return format_box(body)

    def action_open_issues(self) -> None:
        self.panel.show_view(LinearView.PROJECT_ISSUES)

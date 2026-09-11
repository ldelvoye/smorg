"""One list of your projects, grouped by status, each with its milestones' progress."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.binding import Binding

from smorg.integrations.linear.dates import target_label
from smorg.integrations.linear.glyphs import (
    format_progress_bar,
    priority_rank,
    status_color,
    status_disc,
    status_rank,
)
from smorg.integrations.linear.source import Milestone, Project
from smorg.integrations.linear.views import LinearView
from smorg.shell.cards import format_card, format_card_title, format_marks
from smorg.shell.cursor import clamp_cursor, step_cursor
from smorg.shell.format import plain_lines, truncating
from smorg.shell.terminal_palette import StatusColors
from smorg.shell.view_host import GatedBodyView

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

_STATUS_TYPE_RANKS = {"started": 0, "planned": 1, "backlog": 2}
_PERCENT_WIDTH = 3
_MILESTONE_INDENT = "   "


def _status_type_rank(status_type: str) -> int:
    known = _STATUS_TYPE_RANKS.get(status_type)
    if known is not None:
        return known
    return 3


def _ordered(projects: tuple[Project, ...]) -> tuple[Project, ...]:
    def key(project: Project) -> tuple[int, int, str, int, str]:
        return (
            _status_type_rank(project.status_type),
            status_rank(project.status, project.status_type),
            project.status.casefold(),
            priority_rank(project.priority),
            project.name.casefold(),
        )

    return tuple(sorted(projects, key=key))


def _format_milestone_row(milestone: Milestone, accent: str) -> Text:
    row = Text(_MILESTONE_INDENT)
    row.append_text(format_progress_bar(milestone.progress, accent))
    percent = f"{milestone.progress}%".rjust(_PERCENT_WIDTH + 1)
    row.append(percent, style="dim")
    row.append("  ")
    row.append(milestone.name)
    target = target_label(milestone.target_date, "day")
    if target:
        row.append(f" · {target}", style="dim")
    return truncating(row)


def _format_title_row(project: Project, selected: bool, colors: StatusColors, accent: str) -> Text:
    row = Text()
    row.append_text(format_marks(selected, False, accent))
    row.append(" ")
    disc = status_disc(project.status, project.status_type)
    color = status_color(project.status, project.status_type, colors, accent)
    row.append(disc, style=color)
    row.append(" ")
    if selected:
        name_style = "bold"
    else:
        name_style = ""
    row.append(project.name, style=name_style)
    meta: list[str] = []
    if project.lead:
        meta.append(project.lead)
    target = target_label(project.target_date, project.target_resolution)
    if target:
        meta.append(target)
    if meta:
        meta_text = " · ".join(meta)
        row.append(f"  {meta_text}", style="dim")
    return truncating(row)


def _project_groups(projects: tuple[Project, ...]) -> list[tuple[str, str, list[Project]]]:
    groups: list[tuple[str, str, list[Project]]] = []
    current_status = ""
    current_members: list[Project] = []
    for project in projects:
        if project.status != current_status:
            current_status = project.status
            current_members = []
            groups.append((project.status, project.status_type, current_members))
        current_members.append(project)
    return groups


class LinearProjects(GatedBodyView["LinearPanel"]):
    BINDINGS = [
        Binding("up", "cursor_up", "select project", show=False),
        Binding("down", "cursor_down", "select project", show=False),
        Binding("o", "open_selected", "open in Linear", show=False),
        Binding("enter", "open_project", "view project", show=False),
        Binding("escape", "back_to_menu", "back to menu", show=False),
    ]
    DEFAULT_CSS = """
    LinearProjects { align-horizontal: center; }
    LinearProjects > #body { width: 100%; max-width: 120; }
    """

    def selected_item(self) -> Project | None:
        projects = _ordered(self.panel.projects())
        if not projects:
            return None
        index = clamp_cursor(self.cursor, len(projects))
        return projects[index]

    def _move(self, offset: int) -> None:
        projects = _ordered(self.panel.projects())
        if not projects:
            return
        self.cursor = step_cursor(self.cursor, offset, len(projects))
        self.panel.refresh()
        self.scroll_to_selection()

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def action_open_selected(self) -> None:
        project = self.selected_item()
        if project is None:
            return
        webbrowser.open(project.url)

    def action_open_project(self) -> None:
        project = self.selected_item()
        if project is None:
            return
        self.panel.open_project(project)

    def action_back_to_menu(self) -> None:
        self.panel.show_view(LinearView.MENU)

    def render_view(self) -> RenderableType:
        projects = _ordered(self.panel.projects())
        if not projects:
            return Text("no projects", style="dim")
        cursor = clamp_cursor(self.cursor, len(projects))
        selected = projects[cursor]
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        parts: list[RenderableType] = []
        for index, (status, status_type, members) in enumerate(_project_groups(projects)):
            if index > 0:
                parts.append(Text())
            disc = status_disc(status, status_type)
            color = status_color(status, status_type, colors, accent)
            if color == "dim":
                tint = ""
            else:
                tint = color
            title = format_card_title(f"{disc} {status} ({len(members)})", tint)
            body: list[RenderableType] = []
            for member in members:
                if body:
                    body.append(Text())
                body.append(_format_title_row(member, member is selected, colors, accent))
                if member.milestones:
                    for milestone in member.milestones:
                        body.append(_format_milestone_row(milestone, accent))
                else:
                    body.append(Text(f"{_MILESTONE_INDENT}no milestones", style="dim"))
            parts.append(format_card(title, body))
        return Group(*parts)

    def content_lines(self) -> list[str]:
        return plain_lines(self.render_view())

"""The issue page's two pickers: what to open from here, and how far back to go."""

from __future__ import annotations

import webbrowser

from rich.text import Text
from textual.binding import Binding

from smorg.integrations.linear.navigation import (
    Target,
    TargetSection,
    Visit,
    format_project_row,
    format_target_row,
    target_of_issue,
)
from smorg.integrations.linear.source import Issue, Project
from smorg.shell.picker import Picker, Row, Section
from smorg.shell.terminal_palette import StatusColors

_OPEN_HINT = "⏎ open · o open in Linear · esc close"
_TRAIL_HINT = "⏎ go back there · esc close"


class OpenFromPicker(Picker):
    BINDINGS = [
        Binding("up", "cursor_up", "select", show=False),
        Binding("down", "cursor_down", "select", show=False),
        Binding("enter", "confirm", "open", show=False),
        Binding("o", "open_in_linear", "open in Linear", show=False),
        Binding("escape", "close", "close", show=False),
    ]

    def action_open_in_linear(self) -> None:
        value = self.selected_value()
        if not isinstance(value, Target) or not value.url:
            return
        webbrowser.open(value.url)


def open_from_picker(
    issue_id: str,
    sections: tuple[TargetSection, ...],
    colors: StatusColors,
    accent: str,
    cursor: int,
) -> OpenFromPicker:
    picker_sections: list[Section] = []
    for heading, targets in sections:
        rows: list[Row] = []
        for target in targets:
            done = target.status_type == "completed"
            rows.append((format_target_row(target, colors, accent, done), target))
        picker_sections.append((heading, rows))
    return OpenFromPicker(f"open from {issue_id}", picker_sections, _OPEN_HINT, cursor)


class TrailPicker(Picker):
    BINDINGS = [
        Binding("up", "cursor_up", "select", show=False),
        Binding("down", "cursor_down", "select", show=False),
        Binding("enter", "confirm", "go back there", show=False),
        Binding("escape", "close", "close", show=False),
    ]


def _visit_label(visit: Visit) -> str:
    item = visit.item
    if isinstance(item, Project):
        return item.name
    return item.id


def trail_picker(
    visits: list[Visit], root_label: str, colors: StatusColors, accent: str
) -> TrailPicker:
    """Titled by the current page; every earlier visit newest first, and the root last."""
    rows: list[Row] = []
    last = len(visits) - 1
    for index in range(last - 1, -1, -1):
        item = visits[index].item
        if isinstance(item, Issue):
            target = target_of_issue(item)
            row = format_target_row(target, colors, accent, False)
        elif isinstance(item, Project):
            row = format_project_row(item, colors, accent, False)
        else:
            row = Text(item.id)
        rows.append((row, index))
    rows.append((Text(root_label), -1))
    title = f"back from {_visit_label(visits[last])}"
    return TrailPicker(title, [("", rows)], _TRAIL_HINT, 0)

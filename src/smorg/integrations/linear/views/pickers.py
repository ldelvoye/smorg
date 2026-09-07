"""The issue page's two pickers: what to open from here, and how far back to go."""

from __future__ import annotations

import webbrowser

from rich.text import Text
from textual.binding import Binding

from smorg.integrations.linear.navigation import (
    TRAIL_ROOT,
    Target,
    TargetSection,
    Visit,
    format_target_row,
    target_of_issue,
)
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


def trail_picker(visits: list[Visit], colors: StatusColors, accent: str) -> TrailPicker:
    """The current page first (dim), then every earlier visit, and the root `issues` last."""
    rows: list[Row] = []
    last = len(visits) - 1
    for index in range(last, -1, -1):
        current = index == last
        target = target_of_issue(visits[index].issue)
        row = format_target_row(target, colors, accent, current)
        rows.append((row, index))
    rows.append((Text(TRAIL_ROOT), -1))
    cursor = min(1, len(rows) - 1)
    return TrailPicker("back to", [("", rows)], _TRAIL_HINT, cursor)

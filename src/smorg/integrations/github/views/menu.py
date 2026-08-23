"""The menu view: the landing look of the GitHub tab."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from rich.console import Console, Group, RenderableType
from rich.text import Text
from textual.app import RenderResult
from textual.binding import Binding
from textual.widgets import Static

from smorg.integrations.github.views import GitHubView
from smorg.shell.panel import PanelState

if TYPE_CHECKING:
    from smorg.integrations.github.panel import GitHubPanel

_SELECTED_MARK = "▸"
_CHANGED_MARK = "●"
_CHANGE_STYLE = "green"

_DESTINATIONS: tuple[tuple[str, GitHubView], ...] = (("inbox", GitHubView.INBOX),)


def _format_welcome(login: str) -> Text:
    if login:
        return Text(f"welcome back, {login}", style="bold")
    return Text("welcome back", style="bold")


def _format_updates(unseen_count: int) -> Text:
    if unseen_count == 0:
        return Text("you're all caught up", style="dim")
    if unseen_count == 1:
        noun = "update"
    else:
        noun = "updates"
    line = Text()
    line.append(f"{_CHANGED_MARK} ", style=_CHANGE_STYLE)
    line.append(f"{unseen_count} {noun} since you last looked")
    return line


def _format_destination(label: str, selected: bool) -> Text:
    line = Text()
    if selected:
        line.append(f"{_SELECTED_MARK} ", style="bold")
        line.append(label, style="bold")
        line.append("    ")
        line.append("enter to open", style="dim")
    else:
        line.append(f"  {label}")
    return line


class GitHubMenu(Static):
    BINDINGS = [
        Binding("up", "previous_destination", "select destination", show=False),
        Binding("down", "next_destination", "select destination", show=False),
        Binding("enter", "open_destination", "open the selected view", show=False),
    ]
    can_focus = True

    DEFAULT_CSS = """
    GitHubMenu { height: 1fr; content-align: center middle; }
    """

    def __init__(self, panel: GitHubPanel) -> None:
        super().__init__(markup=False)
        self.panel = panel
        self.destination_cursor = 0

    def render(self) -> RenderResult:
        if self.panel.state is PanelState.READY:
            return self.render_content()
        return self.panel.body_text()

    def render_content(self) -> RenderableType:
        profile = self.panel.profile()
        if profile is not None and not profile.unavailable:
            login = profile.login
        else:
            login = ""
        parts: list[RenderableType] = [_format_welcome(login), Text()]
        parts.append(_format_updates(self.panel.unseen_count()))
        parts.append(Text())
        for index, (label, _) in enumerate(_DESTINATIONS):
            parts.append(_format_destination(label, index == self.destination_cursor))
        return Group(*parts)

    def content_lines(self) -> list[str]:
        """render_content flattened to plain text, so the two cannot drift apart."""
        console = Console(width=80, file=io.StringIO(), force_terminal=False)
        with console.capture() as capture:
            console.print(self.render_content())
        return capture.get().splitlines()

    def action_previous_destination(self) -> None:
        self._move_destination(-1)

    def action_next_destination(self) -> None:
        self._move_destination(1)

    def _move_destination(self, offset: int) -> None:
        count = len(_DESTINATIONS)
        self.destination_cursor = (self.destination_cursor + offset) % count
        self.refresh()

    def action_open_destination(self) -> None:
        _, destination = _DESTINATIONS[self.destination_cursor]
        self.panel.show_view(destination)

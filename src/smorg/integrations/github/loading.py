"""The loading view: the octocat and an indeterminate bar, shown before data lands."""

from __future__ import annotations

from rich.console import Group
from rich.text import Text
from textual.app import RenderResult
from textual.timer import Timer
from textual.widgets import Static

_OCTOCAT = (
    "⠀⠀⠀⠀⠀⠀⠀⢀⣠⣤⣤⣶⣶⣶⣶⣤⣤⣄⡀⠀⠀⠀⠀⠀⠀⠀",
    "⠀⠀⠀⠀⢀⣤⣾⣿⣿⠿⠟⠛⠛⠛⠛⠻⠿⣿⣿⣷⣤⡀⠀⠀⠀⠀",
    "⠀⠀⠀⣴⣿⣿⠟⠋⠁⠀⠀⠀⠀⠀⠀⠀⠀⠈⠙⠻⣿⣿⣦⠀⠀⠀",
    "⠀⢀⣾⣿⡿⠁⠀⠀⣴⣦⣄⠀⠀⠀⠀⠀⣀⣤⣶⡀⠈⢿⣿⣷⡀⠀",
    "⠀⣾⣿⡟⠁⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠃⠀⠈⢻⣿⣷⠀",
    "⢠⣿⣿⠁⠀⠀⠀⣠⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⠀⠀⠈⣿⣿⡄",
    "⢸⣿⣿⠀⠀⠀⢰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⣿⣿⡇",
    "⠘⣿⣿⡦⠤⠒⠒⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠧⠤⢴⣿⣿⠃",
    "⠀⢿⣿⣧⡀⠀⢤⡀⠙⠻⠿⣿⣿⣿⣿⣿⡿⠟⠋⠁⠀⢀⣼⣿⡿⠀",
    "⠀⠈⢿⣿⣷⡀⠈⢿⣦⣤⣾⣿⣿⣿⣿⣿⣷⣄⠀⠀⢀⣾⣿⡿⠁⠀",
    "⠀⠀⠀⠻⣿⣿⣦⣄⡉⣿⣿⢿⣿⠉⢻⣿⢿⣿⣠⣴⣿⣿⠟⠀⠀⠀",
    "⠀⠀⠀⠀⠈⠛⢿⣿⣿⣿⣧⣼⣿⣤⣾⣷⣶⣿⣿⡿⠛⠁⠀⠀⠀⠀",
    "⠀⠀⠀⠀⠀⠀⠀⠈⠙⠛⠛⠿⠿⠿⠿⠛⠛⠋⠁⠀⠀⠀⠀⠀⠀⠀",
)

_TRACK_WIDTH = 26
_SEGMENT_WIDTH = 5
_TICK_SECONDS = 0.08


class GitHubLoading(Static):
    DEFAULT_CSS = """
    GitHubLoading { height: 1fr; content-align: center middle; }
    """

    def __init__(self) -> None:
        super().__init__(markup=False)
        self.bar_position = 0
        self.bar_direction = 1
        self.is_animating = False
        self._timer: Timer | None = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(_TICK_SECONDS, self._advance, pause=True)

    def on_show(self) -> None:
        self.is_animating = True
        if self._timer is not None:
            self._timer.resume()

    def on_hide(self) -> None:
        self.is_animating = False
        if self._timer is not None:
            self._timer.pause()

    def _advance(self) -> None:
        limit = _TRACK_WIDTH - _SEGMENT_WIDTH
        next_position = self.bar_position + self.bar_direction
        if next_position <= 0 or next_position >= limit:
            self.bar_direction = -self.bar_direction
        self.bar_position = max(0, min(limit, next_position))
        self.refresh()

    def render(self) -> RenderResult:
        art = [Text(line, style="dim") for line in _OCTOCAT]
        return Group(*art, Text(), self._format_bar())

    def _format_bar(self) -> Text:
        before = self.bar_position
        after = _TRACK_WIDTH - _SEGMENT_WIDTH - before
        bar = Text()
        bar.append("─" * before, style="dim")
        bar.append("━" * _SEGMENT_WIDTH, style="green")
        bar.append("─" * after, style="dim")
        return bar

"""The loading view: the octocat and an indeterminate bar, shown before data lands."""

from __future__ import annotations

from rich.console import Group
from rich.text import Text
from textual.app import RenderResult
from textual.widgets import Static

from smorg.shell.animation import FrameClock

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

    def __init__(self, reason: str, id: str | None = None) -> None:
        super().__init__(markup=False, id=id)
        self.reason = reason
        self.bar_position = 0
        self.bar_direction = 1
        self._clock = FrameClock(self, 1 / _TICK_SECONDS, self._tick)

    @property
    def is_animating(self) -> bool:
        return self._clock.running

    def on_show(self) -> None:
        self._clock.start()

    def on_hide(self) -> None:
        self._clock.stop()

    def _tick(self, elapsed: float) -> None:
        self._advance()

    def _advance(self) -> None:
        limit = _TRACK_WIDTH - _SEGMENT_WIDTH
        next_position = self.bar_position + self.bar_direction
        if next_position <= 0 or next_position >= limit:
            self.bar_direction = -self.bar_direction
        self.bar_position = max(0, min(limit, next_position))
        self.refresh()

    def render(self) -> RenderResult:
        art = [Text(line, style="dim") for line in _OCTOCAT]
        caption = Text(self.reason.center(_TRACK_WIDTH), style="dim")
        return Group(*art, Text(), self._format_bar(), Text(), caption)

    def _format_bar(self) -> Text:
        before = self.bar_position
        after = _TRACK_WIDTH - _SEGMENT_WIDTH - before
        bar = Text()
        bar.append("─" * before, style="dim")
        bar.append("━" * _SEGMENT_WIDTH, style="green")
        bar.append("─" * after, style="dim")
        return bar

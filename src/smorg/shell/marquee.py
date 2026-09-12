"""A bouncing marquee for a row too wide for its space: one tagged span slides, the rest stays."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual.widget import Widget

from smorg.shell.animation import FrameClock

MARQUEE_FPS = 10
MARQUEE_HOLD_TICKS = 10

_MARQUEE_KEY = "marquee"
MARQUEE_STYLE = Style(meta={_MARQUEE_KEY: True})
"""The style a row formatter puts on the span that may slide; the title, usually."""


def _tagged_span(row: Text) -> tuple[int, int] | None:
    for span in row.spans:
        style = span.style
        if isinstance(style, Style) and style.meta.get(_MARQUEE_KEY):
            return span.start, span.end
    return None


def marquee_overflow(row: Text, width: int) -> int:
    """How many columns the row runs past `width`, or zero when it fits or has no tagged span."""
    if width <= 0:
        return 0
    span = _tagged_span(row)
    if span is None:
        return 0
    start, end = span
    fixed = cell_len(row.plain[:start]) + cell_len(row.plain[end:])
    if fixed >= width:
        return 0
    overflow = cell_len(row.plain) - width
    return max(0, overflow)


def marquee_window(row: Text, width: int, offset: int) -> Text:
    """The row fitted to `width` with the tagged span slid `offset` characters, both ends whole."""
    overflow = marquee_overflow(row, width)
    if overflow == 0:
        return row
    span = _tagged_span(row)
    if span is None:
        return row
    start, end = span
    head = row[:start]
    tail = row[end:]
    budget = width - cell_len(head.plain) - cell_len(tail.plain)
    slide = min(offset, overflow)
    window = row[start + slide : end]
    window.truncate(budget, overflow="crop")
    fitted = Text()
    fitted.append_text(head)
    fitted.append_text(window)
    fitted.append_text(tail)
    return fitted


@dataclass
class Marquee:
    """Where a bouncing marquee is: its offset, which way it moves, and the rest left at an end."""

    offset: int = 0
    direction: int = 1
    hold: int = MARQUEE_HOLD_TICKS

    def reset(self) -> None:
        self.offset = 0
        self.direction = 1
        self.hold = MARQUEE_HOLD_TICKS

    def advance(self, overflow: int) -> bool:
        """One tick; True when the offset moved."""
        if overflow <= 0:
            moved = self.offset != 0
            self.reset()
            return moved
        if self.hold > 0:
            self.hold -= 1
            return False
        next_offset = self.offset + self.direction
        if next_offset > overflow or next_offset < 0:
            self.direction = -self.direction
            next_offset = self.offset + self.direction
        self.offset = next_offset
        if next_offset == 0 or next_offset == overflow:
            self.hold = MARQUEE_HOLD_TICKS
        return True


class RowMarquee:
    """A marquee for a widget's selected row, ticking while the widget is shown."""

    def __init__(
        self,
        widget: Widget,
        overflow_of_selected: Callable[[], int],
        on_change: Callable[[], None],
    ) -> None:
        self._marquee = Marquee()
        self._overflow_of_selected = overflow_of_selected
        self._on_change = on_change
        self._clock = FrameClock(widget, MARQUEE_FPS, self._tick)

    @property
    def offset(self) -> int:
        return self._marquee.offset

    def start(self) -> None:
        self._clock.start()

    def stop(self) -> None:
        self._clock.stop()

    def reset(self) -> None:
        self._marquee.reset()

    def _tick(self, elapsed: float) -> None:
        overflow = self._overflow_of_selected()
        moved = self._marquee.advance(overflow)
        if moved:
            self._on_change()

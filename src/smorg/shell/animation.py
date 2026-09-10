"""A frame clock for widgets that animate: ticks while running and shown, frame-counted time."""

from __future__ import annotations

from collections.abc import Callable

from textual.timer import Timer
from textual.widget import Widget


class FrameClock:
    """An `fps` ticker calling `on_tick(elapsed_seconds)` while started and not paused."""

    def __init__(self, widget: Widget, fps: float, on_tick: Callable[[float], None]) -> None:
        self._widget = widget
        self._fps = fps
        self._on_tick = on_tick
        self._timer: Timer | None = None
        self._ticks = 0
        self.running = False
        self._paused = False

    @property
    def elapsed(self) -> float:
        return self._ticks / self._fps

    def start(self) -> None:
        self._ticks = 0
        self.running = True
        if self._timer is None:
            self._timer = self._widget.set_interval(1 / self._fps, self._tick, pause=True)
        if not self._paused:
            self._timer.resume()

    def stop(self) -> None:
        self.running = False
        if self._timer is not None:
            self._timer.pause()

    def pause(self) -> None:
        self._paused = True
        if self._timer is not None:
            self._timer.pause()

    def resume(self) -> None:
        self._paused = False
        if self.running and self._timer is not None:
            self._timer.resume()

    def _tick(self) -> None:
        if not self.running:
            return
        self._ticks += 1
        self._on_tick(self.elapsed)

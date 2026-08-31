"""Transient staged feedback for the refresh keybind.

Only the r key shows this; tab-switch and focus refreshes stay silent, because only a pressed
key needs visible confirmation that it registered.
"""

from __future__ import annotations

from enum import StrEnum

from rich.text import Text
from textual.timer import Timer
from textual.widgets import Static


class RefreshStage(StrEnum):
    """The stages a keybind-triggered refresh passes through, in order. FAILED ends the sequence
    early; the panel itself shows the error.
    """

    CONNECTING = "connecting"
    FETCHING = "fetching"
    DONE = "done"
    FAILED = "failed"


DONE_LINGER_SECONDS = 1.0


class RefreshIndicator(Static):
    """A one-line overlay above the footer showing refresh progress.

    Lives on its own layer (see SmorgApp.CSS) so appearing never reflows the panel; width: auto
    keeps it covering only the cells it draws.
    """

    DEFAULT_CSS = """
    RefreshIndicator {
        layer: refresh-indicator;
        dock: bottom;
        width: auto;
        height: 1;
        margin-bottom: 1;
    }
    """

    def __init__(self, phases: tuple[str, ...] = ()) -> None:
        super().__init__(markup=False)
        self.phases = phases
        self.display = False
        self._hide_timer: Timer | None = None

    @property
    def _total_cells(self) -> int:
        if not self.phases:
            return 3
        return 2 + len(self.phases)

    def show_stage(self, stage: RefreshStage) -> None:
        if self._hide_timer is not None:
            self._hide_timer.stop()
            self._hide_timer = None
        if stage is RefreshStage.FAILED:
            self.display = False
            return
        total = self._total_cells
        if stage is RefreshStage.CONNECTING:
            filled = 1
            label = "connecting…"
        elif stage is RefreshStage.FETCHING:
            filled = 2
            if self.phases:
                label = f"fetching {self.phases[0]}…"
            else:
                label = "fetching…"
        else:
            filled = total
            label = "refreshed"
        self.update(self._format_progress(filled, total, label))
        self.display = True
        # A refresh can finish after its indicator was swapped out for another tab's; a timer on
        # a removed widget raises.
        if stage is RefreshStage.DONE and self.is_mounted:
            self._hide_timer = self.set_timer(DONE_LINGER_SECONDS, self._hide)

    def show_phase(self, index: int) -> None:
        filled = 2 + index
        label = f"fetching {self.phases[index]}…"
        self.update(self._format_progress(filled, self._total_cells, label))
        self.display = True

    def _format_progress(self, filled: int, total: int, label: str) -> Text:
        bar = "▰" * filled + "▱" * (total - filled)
        return Text(f"{bar} {label}", style="dim")

    def _hide(self) -> None:
        self._hide_timer = None
        self.display = False

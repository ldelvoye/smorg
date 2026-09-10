import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from smorg.shell.animation import FrameClock


class _Ticking(Static):
    def __init__(self) -> None:
        super().__init__("")
        self.seen: list[float] = []
        self.clock = FrameClock(self, fps=50, on_tick=self.seen.append)

    def on_show(self) -> None:
        self.clock.resume()

    def on_hide(self) -> None:
        self.clock.pause()


class _Harness(App[None]):
    def compose(self) -> ComposeResult:
        yield _Ticking()


@pytest.mark.asyncio
async def test_elapsed_counts_frames_and_stops_while_hidden():
    async with _Harness().run_test() as pilot:
        widget = pilot.app.query_one(_Ticking)
        widget.clock.start()
        await pilot.pause(0.3)
        assert widget.clock.running is True
        assert widget.seen

        widget.display = False
        await pilot.pause(0.1)
        frozen = len(widget.seen)
        await pilot.pause(0.2)
        assert len(widget.seen) == frozen

        widget.display = True
        await pilot.pause(0.2)
        assert len(widget.seen) > frozen

        widget.clock.stop()
        await pilot.pause(0.1)
        stopped = len(widget.seen)
        await pilot.pause(0.2)
        assert len(widget.seen) == stopped
        assert widget.clock.running is False

"""The shell's picker modal: sections, a cursor over rows only, confirm and close."""

import pytest
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static

from smorg.shell.picker import Picker, Row, Section


class _Picker(Picker):
    BINDINGS = [
        Binding("up", "cursor_up", "up", show=False),
        Binding("down", "cursor_down", "down", show=False),
        Binding("enter", "confirm", "confirm", show=False),
        Binding("escape", "close", "close", show=False),
    ]


class _Harness(App[None]):
    def __init__(
        self, sections: list[Section], cursor: int = 0, title: str = "open from ENG-1"
    ) -> None:
        super().__init__()
        self.sections = sections
        self.start = cursor
        self.picker_title = title
        self.result: object = "unset"

    def compose(self) -> ComposeResult:
        yield Static("page")

    def open_picker(self) -> None:
        picker = _Picker(self.picker_title, self.sections, "⏎ open · esc close", self.start)
        self.push_screen(picker, self._picked)

    def _picked(self, value: object | None) -> None:
        self.result = value


def _sections() -> list[Section]:
    return [
        ("parent", [(Text("ENG-0 epic"), "ENG-0")]),
        ("sub-issues (0/2)", [(Text("ENG-2 a"), "ENG-2"), (Text("ENG-3 b"), "ENG-3")]),
    ]


@pytest.mark.asyncio
async def test_the_cursor_skips_headings_wraps_and_confirm_dismisses_with_the_value():
    app = _Harness(_sections())
    async with app.run_test() as pilot:
        app.open_picker()
        await pilot.pause()
        picker = app.screen
        assert isinstance(picker, Picker)
        lines = picker.content_lines()
        assert lines[0] == "parent"
        assert lines[1].startswith("▸ ")
        assert "sub-issues (0/2)" in lines

        await pilot.press("up")
        assert picker.selected_value() == "ENG-3"
        await pilot.press("down", "down")
        assert picker.selected_value() == "ENG-2"

        await pilot.press("enter")
        await pilot.pause()
    assert app.result == "ENG-2"


@pytest.mark.asyncio
async def test_close_dismisses_with_none_and_the_start_cursor_is_honored():
    app = _Harness(_sections(), cursor=2, title="open from [red]ENG-9[/red]")
    async with app.run_test() as pilot:
        app.open_picker()
        await pilot.pause()
        picker = app.screen
        assert isinstance(picker, Picker)
        assert picker.selected_value() == "ENG-3"
        border_title = picker.query_one(".box").border_title
        assert border_title is not None
        assert "\\[red]ENG-9\\[/red]" in border_title
        await pilot.press("escape")
        await pilot.pause()
    assert app.result is None


@pytest.mark.asyncio
async def test_the_cursor_still_moves_and_stays_visible_when_the_list_overflows():
    rows: list[Row] = [(Text(f"ENG-{index} row"), f"ENG-{index}") for index in range(60)]
    app = _Harness([("many", rows)])
    async with app.run_test(size=(80, 24)) as pilot:
        app.open_picker()
        await pilot.pause()
        picker = app.screen
        assert isinstance(picker, Picker)
        await pilot.press("down", "down", "down")
        await pilot.pause()
        assert picker.cursor == 3
        for _ in range(40):
            await pilot.press("down")
        await pilot.pause()
        assert picker.cursor == 43
        box = picker.query_one(".box", VerticalScroll)
        assert box.scroll_offset.y > 0
        await pilot.press("enter")
        await pilot.pause()
    assert app.result == "ENG-43"


@pytest.mark.asyncio
async def test_rows_truncate_instead_of_wrapping():
    long_row: list[Row] = [(Text("ENG-0 " + "x" * 200), "ENG-0")]
    app = _Harness([("one", long_row)])
    async with app.run_test(size=(80, 24)) as pilot:
        app.open_picker()
        await pilot.pause()
        picker = app.screen
        assert isinstance(picker, Picker)
        body = picker.query_one("#picker-body", Static)
        lines = [body.render_line(y).text.rstrip() for y in range(body.size.height)]
        with_x = [line for line in lines if "x" in line]
    assert len(with_x) == 1
    assert "ENG-0" in with_x[0]
    assert with_x[0].endswith("…")

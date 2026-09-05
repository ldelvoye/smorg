"""A modal list to pick one thing from: titled sections, a cursor over rows, one result."""

from __future__ import annotations

import io

from rich.console import Console
from rich.text import Text
from textual.app import ComposeResult, RenderResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from smorg.shell.cards import SELECTED_MARK
from smorg.shell.modal import ModalBox
from smorg.shell.panel import GutteredScroll

Row = tuple[Text, object]
Section = tuple[str, list[Row]]

_HEADING_STYLE = "dim"
_HINT_STYLE = "dim"


class _PickerBody(Static):
    DEFAULT_CSS = """
    _PickerBody { text-wrap: nowrap; text-overflow: ellipsis; }
    """

    def __init__(self, picker: Picker) -> None:
        super().__init__(markup=False, id="picker-body")
        self._picker = picker

    def render(self) -> RenderResult:
        return self._picker.render_content()


class Picker(ModalBox):
    """Extend this, declare your own BINDINGS for cursor_up/cursor_down/confirm/close, and
    read the chosen row's value from the dismiss callback (None when closed).
    """

    DEFAULT_CSS = """
    Picker > .box { max-height: 80%; max-width: 90%; }
    """

    def __init__(self, title: str, sections: list[Section], hint: str, cursor: int = 0) -> None:
        super().__init__()
        self._title = title
        self._sections = sections
        self._hint = hint
        self.cursor = cursor

    def compose(self) -> ComposeResult:
        body = GutteredScroll(_PickerBody(self), classes="box")
        body.can_focus = False
        body.border_title = Text(self._title)
        yield body

    def on_mount(self) -> None:
        self.call_after_refresh(self._scroll_selected_into_view)

    def rows(self) -> list[Row]:
        rows: list[Row] = []
        for _, section_rows in self._sections:
            rows.extend(section_rows)
        return rows

    def selected_value(self) -> object | None:
        rows = self.rows()
        if not rows:
            return None
        index = min(self.cursor, len(rows) - 1)
        _, value = rows[index]
        return value

    def render_content(self) -> Text:
        """One Text, a line per row: a Group would measure as zero width inside the auto-sized
        box, while a multi-line Text measures as its longest line and truncates each line.
        """
        rows = self.rows()
        selected = min(self.cursor, max(len(rows) - 1, 0))
        lines: list[Text] = []
        row_index = 0
        for section_index, (heading, section_rows) in enumerate(self._sections):
            if section_index > 0:
                lines.append(Text())
            if heading:
                lines.append(Text(heading, style=_HEADING_STYLE))
            for rendered, _ in section_rows:
                line = Text()
                if row_index == selected:
                    line.append(f"{SELECTED_MARK} ", style="bold")
                else:
                    line.append("  ")
                line.append_text(rendered)
                lines.append(line)
                row_index += 1
        lines.append(Text())
        lines.append(Text(self._hint, style=_HINT_STYLE))
        content = Text("\n").join(lines)
        content.no_wrap = True
        content.overflow = "ellipsis"
        return content

    def content_lines(self) -> list[str]:
        """render_content flattened to plain text, so the two cannot drift apart."""
        console = Console(width=80, file=io.StringIO(), force_terminal=False)
        with console.capture() as capture:
            console.print(self.render_content(), no_wrap=True, overflow="ellipsis")
        return capture.get().splitlines()

    def _selected_line(self) -> int:
        """The rendered line the cursor's row sits on, counting headings and separators."""
        rows = self.rows()
        selected = min(self.cursor, max(len(rows) - 1, 0))
        line = 0
        row_index = 0
        for section_index, (heading, section_rows) in enumerate(self._sections):
            if section_index > 0:
                line += 1
            if heading:
                line += 1
            for _ in section_rows:
                if row_index == selected:
                    return line
                row_index += 1
                line += 1
        return line

    def _scroll_selected_into_view(self) -> None:
        if not self.is_mounted:
            return
        box = self.query_one(".box", VerticalScroll)
        target = self._selected_line()
        top = int(box.scroll_offset.y)
        height = box.scrollable_content_region.height
        if height <= 0:
            return
        if target < top:
            box.scroll_to(y=target, animate=False)
        elif target >= top + height:
            box.scroll_to(y=target - height + 1, animate=False)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def action_cursor_down(self) -> None:
        self._move(1)

    def _move(self, offset: int) -> None:
        rows = self.rows()
        if not rows:
            return
        index = min(self.cursor, len(rows) - 1)
        self.cursor = (index + offset) % len(rows)
        self.query_one(_PickerBody).refresh()
        self._scroll_selected_into_view()

    def action_confirm(self) -> None:
        self.dismiss(self.selected_value())

    def action_close(self) -> None:
        self.dismiss(None)

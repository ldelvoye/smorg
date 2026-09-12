"""A modal list to pick one thing from: titled sections, a cursor over rows, one result."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from smorg.shell.cards import SELECTED_MARK
from smorg.shell.cursor import clamp_cursor, step_cursor
from smorg.shell.format import plain_lines, truncating
from smorg.shell.marquee import RowMarquee, marquee_overflow, marquee_window
from smorg.shell.modal import ModalBox
from smorg.shell.panel import GutteredScroll, ViewBody

Row = tuple[Text, object]
Section = tuple[str, list[Row]]

_HEADING_STYLE = "dim"
_HINT_STYLE = "dim"


class Picker(ModalBox):
    """Extend this, declare your own BINDINGS for cursor_up/cursor_down/confirm/close, and
    read the chosen row's value from the dismiss callback (None when closed).
    """

    DEFAULT_CSS = """
    Picker > .box { max-height: 80%; max-width: 90%; }
    /* Textual renders a bare Text as its own Content, without Rich's no_wrap and overflow
     * flags, so the truncation has to come from CSS. */
    Picker #picker-body { text-wrap: nowrap; text-overflow: ellipsis; }
    """

    def __init__(self, title: str, sections: list[Section], hint: str, cursor: int = 0) -> None:
        super().__init__()
        self._title = title
        self._sections = sections
        self._hint = hint
        self.cursor = cursor
        self._rows: list[Row] = []
        for _, section_rows in self._sections:
            self._rows.extend(section_rows)
        self.marquee = RowMarquee(self, self._selected_overflow, self._refresh_body)

    def compose(self) -> ComposeResult:
        body = GutteredScroll(ViewBody(self.render_content, id="picker-body"), classes="box")
        body.can_focus = False
        body.border_title = Text(self._title)
        yield body

    def on_mount(self) -> None:
        self.call_after_refresh(self._scroll_selected_into_view)
        self.marquee.start()

    def on_screen_suspend(self) -> None:
        self.marquee.stop()

    def on_screen_resume(self) -> None:
        self.marquee.start()

    def rows(self) -> list[Row]:
        return self._rows

    def selected_value(self) -> object | None:
        rows = self.rows()
        if not rows:
            return None
        index = clamp_cursor(self.cursor, len(rows))
        _, value = rows[index]
        return value

    def render_content(self) -> Text:
        """One Text, a line per row: a Group would measure as zero width inside the auto-sized
        box, while a multi-line Text measures as its longest line and truncates each line.
        """
        rows = self.rows()
        selected = clamp_cursor(self.cursor, len(rows))
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
                    row_width = self._body_width() - len(f"{SELECTED_MARK} ")
                    fitted = marquee_window(rendered, row_width, self.marquee.offset)
                    line.append_text(fitted)
                else:
                    line.append("  ")
                    line.append_text(rendered)
                lines.append(line)
                row_index += 1
        lines.append(Text())
        lines.append(Text(self._hint, style=_HINT_STYLE))
        content = Text("\n").join(lines)
        return truncating(content)

    def content_lines(self) -> list[str]:
        """render_content flattened to plain text, so the two cannot drift apart."""
        return plain_lines(self.render_content())

    def _body_width(self) -> int:
        if not self.is_mounted:
            return 0
        body = self.query_one("#picker-body", Static)
        return body.content_size.width

    def _selected_row(self) -> Text | None:
        rows = self.rows()
        if not rows:
            return None
        index = clamp_cursor(self.cursor, len(rows))
        rendered, _ = rows[index]
        return rendered

    def _selected_overflow(self) -> int:
        rendered = self._selected_row()
        if rendered is None:
            return 0
        width = self._body_width() - len(f"{SELECTED_MARK} ")
        return marquee_overflow(rendered, width)

    def _refresh_body(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#picker-body", Static).refresh()

    def _selected_line(self) -> int:
        """The rendered line the cursor's row sits on, counting headings and separators."""
        rows = self.rows()
        selected = clamp_cursor(self.cursor, len(rows))
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
        self.cursor = step_cursor(self.cursor, offset, len(rows))
        self.marquee.reset()
        self.query_one("#picker-body", Static).refresh()
        self._scroll_selected_into_view()

    def action_confirm(self) -> None:
        self.dismiss(self.selected_value())

    def action_close(self) -> None:
        self.dismiss(None)

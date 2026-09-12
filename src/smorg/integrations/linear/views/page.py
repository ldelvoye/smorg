"""The two-pane scaffold shared by Linear's issue and project pages."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static

from smorg.core.contract import Item
from smorg.integrations.linear.navigation import Visit, format_trail
from smorg.integrations.linear.views.pickers import trail_picker
from smorg.shell.format import plain_lines
from smorg.shell.panel import GutteredScroll, ViewBody
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

NARROW_BELOW = 90
SIDEBAR_WIDTH = 34
BACK_HINT_PREFIX = "‹ esc — "
SUBHEADING_STYLE = "dim"
_BACK_HINT_GAP = 3


class LinearPage(Horizontal, HostedView):
    """A reading column beside a docked properties sidebar, folding to one column when narrow."""

    BINDINGS = [
        Binding("backspace", "show_trail", "back to…", show=False),
        Binding("o", "open_in_linear", "open in Linear", show=False),
        Binding("escape", "back", "back", show=False),
    ]

    DEFAULT_CSS = f"""
    LinearPage {{ max-width: 120; }}
    LinearPage > .reading {{ width: 1fr; }}
    LinearPage > .sidebar {{ dock: right; width: {SIDEBAR_WIDTH}; }}
    """

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__()
        self.panel = panel
        self.narrow = False

    def page_item(self) -> Item | None:
        raise NotImplementedError

    def render_reading(self, narrow: bool) -> RenderableType:
        raise NotImplementedError

    def render_sidebar(self) -> RenderableType:
        raise NotImplementedError

    def compose(self) -> ComposeResult:
        reading_body = ViewBody(self._render_reading, id="reading-body")
        reading = GutteredScroll(reading_body, classes="reading")
        reading.can_focus = True
        yield reading
        sidebar_body = ViewBody(self._render_sidebar, id="sidebar-body")
        sidebar = GutteredScroll(sidebar_body, classes="sidebar")
        sidebar.can_focus = False
        yield sidebar

    def _render_reading(self) -> RenderableType:
        return self.render_reading(self.narrow)

    def _render_sidebar(self) -> RenderableType:
        return self.render_sidebar()

    def on_mount(self) -> None:
        self._sync_columns()

    def on_resize(self, event: events.Resize) -> None:
        self._sync_columns()

    def focus(self, scroll_visible: bool = True):
        self.query_one(".reading", GutteredScroll).focus(scroll_visible)
        return self

    def reading_scroll_y(self) -> int:
        if not self.is_mounted:
            return 0
        return int(self.query_one(".reading", GutteredScroll).scroll_offset.y)

    def restore_view_state(self, visit: Visit) -> None:
        if not self.is_mounted:
            return
        reading = self.query_one(".reading", GutteredScroll)
        reading.scroll_to(y=visit.scroll_y, animate=False)

    def _back_hint(self) -> str:
        labels = self.panel.trail_labels()
        if len(labels) < 2:
            root_label = str(self.panel.trail.root)
            return f"{BACK_HINT_PREFIX}{root_label}"
        return f"{BACK_HINT_PREFIX}{labels[-2]}"

    def _budget(self) -> int:
        if not self.is_mounted:
            return 80
        body = self.query_one("#reading-body", Static)
        if body.size.width > 0:
            return body.size.width
        return 80

    def _sync_columns(self) -> None:
        if not self.is_mounted:
            return
        self.narrow = self.size.width < NARROW_BELOW
        self.query_one(".sidebar", GutteredScroll).display = not self.narrow
        self.refresh_content()

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#reading-body", Static).refresh(layout=True)
        self.query_one("#sidebar-body", Static).refresh(layout=True)

    def content_lines(self) -> list[str]:
        """render_reading and render_sidebar flattened to plain text, reading column first."""
        item = self.page_item()
        if item is None:
            return []
        budget = self._budget()
        lines = plain_lines(self.render_reading(self.narrow), budget)
        if not self.narrow:
            lines.extend(plain_lines(self.render_sidebar(), budget))
        return lines

    def _format_trail_lines(self, narrow: bool) -> list[RenderableType]:
        hint = Text(self._back_hint(), style="dim")
        labels = self.panel.trail_labels()
        root_label = str(self.panel.trail.root)
        if narrow:
            trail = format_trail(labels, self._budget(), root_label)
            return [hint, trail]
        budget = self._budget() - hint.cell_len - _BACK_HINT_GAP
        trail = format_trail(labels, budget, root_label)
        line = Table.grid(expand=True)
        line.add_column(no_wrap=True)
        line.add_column(justify="right", no_wrap=True, overflow="ellipsis")
        line.add_row(hint, trail)
        return [line]

    def action_show_trail(self) -> None:
        colors = self.panel.status_colors()
        accent = self.panel.accent()
        root_label = str(self.panel.trail.root)
        picker = trail_picker(self.panel.trail.visits, root_label, colors, accent)
        self.app.push_screen(picker, self._trail_picked)

    def _trail_picked(self, value: object | None) -> None:
        if not isinstance(value, int):
            return
        self.panel.go_back_to(value)

    def action_back(self) -> None:
        self.panel.go_back()

    def action_open_in_linear(self) -> None:
        item = self.page_item()
        if item is None:
            return
        webbrowser.open(item.url)

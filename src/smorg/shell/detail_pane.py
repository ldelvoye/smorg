"""The default details display: a scrollable pane under the body, toggled per item and
scrolled through the panel's own actions.

A panel opts in by extending SplitDetailPanel instead of Panel; render_detail draws each
item's cached detail, and an integration overrides it for a custom shape.
"""

from __future__ import annotations

from rich.console import RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from smorg.core.contract import Item
from smorg.shell.panel import Panel, ScrollGutter


class SplitDetailPanel(Panel):
    """Extend this for the default details display; override render_detail for a custom
    shape. Declare your own key bindings for its actions — this class ships none.
    """

    DEFAULT_CSS = """
    SplitDetailPanel > #detail {
        display: none;
        height: 60%;
        border-top: solid $primary;
        /* Hidden — the gutter widget shows scroll position instead; mouse
         * wheel and shift+up/down still work since both scroll the
         * container's offset directly rather than dragging the bar. */
        scrollbar-size-vertical: 0;
    }
    SplitDetailPanel > #detail.-open { display: block; }
    /* One blank row so the last line of detail content never sits flush
     * against the region's bottom edge. */
    SplitDetailPanel > #detail > #detail-content { padding-bottom: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.detail_open = False
        self._detail_target: tuple[str, str] | None = None
        self._detail_anchor: tuple[bool, tuple[str, str] | None] | None = None

    def compose(self) -> ComposeResult:
        yield from super().compose()
        detail = VerticalScroll(
            Static(markup=False, id="detail-content"), ScrollGutter(), id="detail"
        )
        # The panel keeps focus; the region is scrolled through panel actions, never
        # focused itself.
        detail.can_focus = False
        yield detail

    def render_detail(self, item: Item, detail: object) -> RenderableType:
        """Overridden by an integration. The base names the item only."""
        return Text(item.id)

    def is_detail_showing(self, item: Item) -> bool:
        return self.detail_open and self._detail_target == self.detail_key(item)

    def detail_keys_in_use(self) -> set[tuple[str, str]]:
        """Cache keys pruning must keep beyond the shown items'; the base pins the pane's target."""
        if self._detail_target is not None:
            return {self._detail_target}
        return set()

    def action_toggle_detail(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        key = self.detail_key(item)
        if self.detail_open and key == self._detail_target:
            self.close_detail()
            return
        self.detail_open = True
        self._detail_target = key
        self.request_detail(item)
        self._refresh_detail()

    def close_detail(self) -> None:
        self.detail_open = False
        self._detail_target = None
        self._refresh_detail()

    def action_scroll_detail_up(self) -> None:
        if self.detail_open and self.is_mounted:
            self.query_one("#detail", VerticalScroll).scroll_relative(y=-1, animate=False)

    def action_scroll_detail_down(self) -> None:
        if self.detail_open and self.is_mounted:
            self.query_one("#detail", VerticalScroll).scroll_relative(y=1, animate=False)

    def _format_detail(self) -> RenderableType:
        item = self.selected_item()
        if item is None or not self.detail_open:
            return Text()
        key = self.detail_key(item)
        if key in self._details:
            return self.render_detail(item, self._details[key])
        if self._detail_pending == key:
            return Text("loading…")
        if key in self._detail_errors:
            return Text(f"could not load: {self._detail_errors[key]}")
        return Text("press enter to load")

    def _refresh_detail(self) -> None:
        if not self.is_mounted:
            return
        region = self.query_one("#detail", VerticalScroll)
        region.set_class(self.detail_open, "-open")
        self.query_one("#detail-content", Static).update(self._format_detail())
        # Only reset scroll when the shown subject changes. Panel.refresh() also runs for
        # unrelated reasons (shell repaints, focus regain), and resetting on every one would
        # throw away the reader's scroll position.
        item = self.selected_item()
        anchor = (self.detail_open, self.detail_key(item) if item is not None else None)
        if anchor != self._detail_anchor:
            self._detail_anchor = anchor
            region.scroll_home(animate=False)

    def refresh(
        self, *regions, repaint: bool = True, layout: bool = False, recompose: bool = False
    ):
        if self.is_mounted:
            self._refresh_detail()
        return super().refresh(*regions, repaint=repaint, layout=layout, recompose=recompose)

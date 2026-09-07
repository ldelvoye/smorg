"""A panel that swaps between full views, one widget per member of the integration's view enum."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from rich.console import RenderableType
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from smorg.shell.panel import Panel, PanelState, ViewBody


class HostedView(Widget):
    """What a ViewHostPanel needs from each view it swaps between, on top of being a widget."""

    def content_lines(self) -> list[str]:
        """The view flattened to plain text, so ready_text and tests see what the screen shows."""
        raise NotImplementedError

    def refresh_content(self) -> None:
        """Repaint whatever the view draws from its panel's state."""
        raise NotImplementedError


class GatedBodyView[P: Panel](Vertical, HostedView):
    """A hosted view that is one body: render_view() while the panel is READY, otherwise the
    panel's own state text.
    """

    def __init__(self, panel: P) -> None:
        super().__init__()
        self.panel = panel

    def compose(self) -> ComposeResult:
        yield ViewBody(self._render_body, id="body")

    def render_view(self) -> RenderableType:
        """The view's drawing in the READY state; every subclass overrides it."""
        raise NotImplementedError

    def _render_body(self) -> RenderableType:
        if self.panel.state is PanelState.READY:
            return self.render_view()
        return self.panel.body_text()

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#body", Static).refresh()


class ViewHostPanel[V: Enum](Panel):
    can_focus = False

    def __init__(self, landing: V) -> None:
        super().__init__()
        self.active_view = landing

    def view_classes(self) -> dict[V, type[HostedView]]:
        """Each view and the widget class that draws it; every host overrides this."""
        raise NotImplementedError

    def views_shown(self) -> bool:
        """Whether the views are on screen at all; a loading takeover says no while it lasts."""
        return True

    def on_mount(self) -> None:
        self._sync_view_display()

    def show_view(self, view: V) -> None:
        self.active_view = view
        self._sync_view_display()
        if self.views_shown():
            self.active_widget().focus()
        self.refresh()

    def focus(self, scroll_visible: bool = True):
        if not self.views_shown():
            return super().focus(scroll_visible)
        self.active_widget().focus(scroll_visible)
        return self

    def active_widget(self) -> HostedView:
        view_class = self.view_classes()[self.active_view]
        return self.query_one(view_class)

    def _sync_view_display(self) -> None:
        shown = self.views_shown()
        for view, view_class in self.view_classes().items():
            self.query_one(view_class).display = shown and view is self.active_view
        if shown and self.has_focus:
            self.active_widget().focus()

    def _refresh_body(self, repaint: bool, layout: bool) -> None:
        """Every view repaints itself; one with an auto-height body passes layout=True itself."""
        self._sync_view_display()
        for view_class in self.view_classes().values():
            self.query_one(view_class).refresh_content()

    def help_bindings(self) -> Iterable[object]:
        view_class = self.view_classes()[self.active_view]
        return view_class.BINDINGS

    def ready_text(self) -> str:
        if not self.is_mounted:
            return super().ready_text()
        return "\n".join(self.active_widget().content_lines())

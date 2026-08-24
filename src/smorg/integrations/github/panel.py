"""GitHub's tab: a host panel that swaps between full views owned by this integration."""

from __future__ import annotations

from collections.abc import Iterable

from rich.console import RenderableType
from textual.app import ComposeResult
from textual.types import NoActiveAppError

from smorg.core.contract import Item
from smorg.integrations.github.loading import GitHubLoading
from smorg.integrations.github.source import Profile, PullRequest
from smorg.integrations.github.views import GitHubView
from smorg.integrations.github.views.inbox import GitHubInbox
from smorg.integrations.github.views.menu import GitHubMenu
from smorg.shell.panel import Panel, PanelState
from smorg.shell.terminal_palette import TerminalPalette, relative_luminance

_GREEN_RAMP_DARK = ("#006d32", "#26a641", "#39d353", "#7ee787")
_GREEN_RAMP_LIGHT = ("#aceebb", "#4ac26b", "#1a7f37", "#044f1e")


def _ramp_for_background(background: tuple[int, int, int] | None) -> tuple[str, str, str, str]:
    if background is None:
        return _GREEN_RAMP_DARK
    if relative_luminance(background) > 0.5:
        return _GREEN_RAMP_LIGHT
    return _GREEN_RAMP_DARK


class GitHubPanel(Panel):
    can_focus = False

    def __init__(self) -> None:
        super().__init__()
        self.active_view = GitHubView.MENU

    def compose(self) -> ComposeResult:
        yield GitHubLoading()
        yield GitHubMenu(self)
        yield GitHubInbox(self)

    def on_mount(self) -> None:
        self._sync_view_display()

    def show_view(self, view: GitHubView) -> None:
        self.active_view = view
        self._sync_view_display()
        if self.state is not PanelState.LOADING:
            self._active_view_widget().focus()
        self.refresh()

    def focus(self, scroll_visible: bool = True):
        if self.state is PanelState.LOADING:
            return super().focus(scroll_visible)
        self._active_view_widget().focus(scroll_visible)
        return self

    def _active_view_widget(self) -> GitHubMenu | GitHubInbox:
        if self.active_view is GitHubView.MENU:
            return self._menu()
        return self._inbox()

    def _sync_view_display(self) -> None:
        is_loading = self.state is PanelState.LOADING
        # Focusable only during the loading takeover; at any other time it would sit in the tab
        # order as a bindingless focus stop.
        self.can_focus = is_loading
        self.query_one(GitHubLoading).display = is_loading
        self._menu().display = not is_loading and self.active_view is GitHubView.MENU
        self._inbox().display = not is_loading and self.active_view is GitHubView.INBOX
        if not is_loading and self.has_focus:
            self._active_view_widget().focus()

    def _menu(self) -> GitHubMenu:
        return self.query_one(GitHubMenu)

    def _inbox(self) -> GitHubInbox:
        return self.query_one(GitHubInbox)

    def refresh(
        self, *regions, repaint: bool = True, layout: bool = False, recompose: bool = False
    ):
        if self.is_mounted:
            self._sync_view_display()
            self._menu().refresh(repaint=repaint, layout=layout)
        return super().refresh(*regions, repaint=repaint, layout=layout, recompose=recompose)

    def help_bindings(self) -> Iterable[object]:
        if self.active_view is GitHubView.MENU:
            return GitHubMenu.BINDINGS
        return GitHubInbox.BINDINGS

    def pull_requests(self) -> tuple[PullRequest, ...]:
        prs = [item for item in self.items if isinstance(item, PullRequest)]
        return tuple(prs)

    def profile(self) -> Profile | None:
        for item in self.items:
            if isinstance(item, Profile):
                return item
        return None

    def green_ramp(self) -> tuple[str, str, str, str]:
        """GitHub's contribution greens, picked to sit on this terminal's background."""
        try:
            palette = getattr(self.app, "palette", None)
        except NoActiveAppError:
            return _ramp_for_background(None)
        if isinstance(palette, TerminalPalette):
            return _ramp_for_background(palette.background)
        return _ramp_for_background(None)

    def unseen_count(self) -> int:
        integration_id = self.integration_id
        changed = [pr for pr in self.pull_requests() if self.seen.is_changed(integration_id, pr)]
        return len(changed)

    def mark_all_seen(self) -> None:
        """Mark every shown pull request seen; other item kinds never enter the store."""
        self.seen.mark_all_seen(self.integration_id, self.pull_requests())
        self._save_seen()
        self.refresh()

    def selected_item(self) -> PullRequest | None:
        if self.active_view is GitHubView.MENU:
            return None
        if not self.is_mounted:
            return None
        return self._inbox().selected_item()

    def render_detail(self, item: Item, detail: object) -> RenderableType:
        if not self.is_mounted:
            return super().render_detail(item, detail)
        return self._inbox().render_detail(item, detail)

    def ready_text(self) -> str:
        if not self.is_mounted:
            return super().ready_text()
        if self.active_view is GitHubView.MENU:
            return "\n".join(self._menu().content_lines())
        return "\n".join(self._inbox().content_lines())

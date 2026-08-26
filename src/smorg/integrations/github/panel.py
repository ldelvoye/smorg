"""GitHub's tab: a host panel that swaps between full views owned by this integration."""

from __future__ import annotations

from collections.abc import Iterable

from textual.app import ComposeResult

from smorg.core.contract import Item
from smorg.integrations.github.loading import GitHubLoading
from smorg.integrations.github.source import Profile, PullRequest, PushedBranch, PushedBranches
from smorg.integrations.github.views import GitHubView
from smorg.integrations.github.views.inbox import GitHubInbox
from smorg.integrations.github.views.menu import GitHubMenu
from smorg.integrations.github.views.pull_request import GitHubPullRequestView
from smorg.integrations.github.views.pushed import GitHubPushedBranches
from smorg.shell.panel import Panel, PanelState
from smorg.shell.terminal_palette import relative_luminance

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
        self.viewed: PullRequest | None = None

    def compose(self) -> ComposeResult:
        yield GitHubLoading("connecting to github", id="loading")
        yield GitHubMenu(self)
        yield GitHubInbox(self)
        yield GitHubPullRequestView(self)
        yield GitHubPushedBranches(self)

    def on_mount(self) -> None:
        self._sync_view_display()

    def show_view(self, view: GitHubView) -> None:
        self.active_view = view
        self._sync_view_display()
        if self.state is not PanelState.LOADING:
            self._active_view_widget().focus()
        self.refresh()

    def open_pull_request(self, pr: PullRequest) -> None:
        """Show one pull request full screen; its detail loads while the header renders."""
        self.viewed = pr
        self.request_detail(pr)
        self.mark_seen(pr)
        self.show_view(GitHubView.PULL_REQUEST)

    def close_pull_request(self) -> None:
        self.viewed = None
        self.show_view(GitHubView.INBOX)

    def reload_viewed(self) -> None:
        if self.viewed is None:
            return
        self.reload_detail(self.viewed)
        self.refresh()

    def focus(self, scroll_visible: bool = True):
        if self.state is PanelState.LOADING:
            return super().focus(scroll_visible)
        self._active_view_widget().focus(scroll_visible)
        return self

    def _active_view_widget(
        self,
    ) -> GitHubMenu | GitHubInbox | GitHubPullRequestView | GitHubPushedBranches:
        if self.active_view is GitHubView.MENU:
            return self._menu()
        if self.active_view is GitHubView.INBOX:
            return self._inbox()
        if self.active_view is GitHubView.PULL_REQUEST:
            return self._pull_request()
        return self._pushed_branches()

    def _sync_view_display(self) -> None:
        is_loading = self.state is PanelState.LOADING
        # Focusable only during the loading takeover; at any other time it would sit in the tab
        # order as a bindingless focus stop.
        self.can_focus = is_loading
        self._loading().display = is_loading
        self._menu().display = not is_loading and self.active_view is GitHubView.MENU
        self._inbox().display = not is_loading and self.active_view is GitHubView.INBOX
        showing_pr = not is_loading and self.active_view is GitHubView.PULL_REQUEST
        self._pull_request().display = showing_pr
        showing_pushed = not is_loading and self.active_view is GitHubView.PUSHED_BRANCHES
        self._pushed_branches().display = showing_pushed
        if not is_loading and self.has_focus:
            self._active_view_widget().focus()

    def _loading(self) -> GitHubLoading:
        return self.query_one("#loading", GitHubLoading)

    def _menu(self) -> GitHubMenu:
        return self.query_one(GitHubMenu)

    def _inbox(self) -> GitHubInbox:
        return self.query_one(GitHubInbox)

    def _pull_request(self) -> GitHubPullRequestView:
        return self.query_one(GitHubPullRequestView)

    def _pushed_branches(self) -> GitHubPushedBranches:
        return self.query_one(GitHubPushedBranches)

    def refresh(
        self, *regions, repaint: bool = True, layout: bool = False, recompose: bool = False
    ):
        # Each view repaints its own way: the menu is a Static refreshed directly below, the
        # inbox's body rides the base Panel.refresh's #body query in super().refresh(), and the
        # pull request and pushed-branches views repaint their own children in refresh_content().
        if self.is_mounted:
            self._sync_view_display()
            self._menu().refresh(repaint=repaint, layout=layout)
            self._pull_request().refresh_content()
            self._pushed_branches().refresh_content()
        return super().refresh(*regions, repaint=repaint, layout=layout, recompose=recompose)

    def help_bindings(self) -> Iterable[object]:
        if self.active_view is GitHubView.MENU:
            return GitHubMenu.BINDINGS
        if self.active_view is GitHubView.INBOX:
            return GitHubInbox.BINDINGS
        if self.active_view is GitHubView.PULL_REQUEST:
            return GitHubPullRequestView.BINDINGS
        return GitHubPushedBranches.BINDINGS

    def pull_requests(self) -> tuple[PullRequest, ...]:
        prs = [item for item in self.items if isinstance(item, PullRequest)]
        return tuple(prs)

    def profile(self) -> Profile | None:
        for item in self.items:
            if isinstance(item, Profile):
                return item
        return None

    def pushed_branches(self) -> PushedBranches | None:
        for item in self.items:
            if isinstance(item, PushedBranches):
                return item
        return None

    def green_ramp(self) -> tuple[str, str, str, str]:
        """GitHub's contribution greens, picked to sit on this terminal's background."""
        return _ramp_for_background(self._terminal_background())

    def seen_items(self) -> tuple[Item, ...]:
        """The items that participate in seen-state; the profile stays out of the store."""
        container = self.pushed_branches()
        if container is None:
            branches: tuple[PushedBranch, ...] = ()
        else:
            branches = container.branches
        return (*self.pull_requests(), *branches)

    def unseen_pr_count(self) -> int:
        integration_id = self.integration_id
        changed = [pr for pr in self.pull_requests() if self.seen.is_changed(integration_id, pr)]
        return len(changed)

    def unseen_branch_count(self) -> int:
        container = self.pushed_branches()
        if container is None:
            return 0
        integration_id = self.integration_id
        changed = [
            branch for branch in container.branches if self.seen.is_changed(integration_id, branch)
        ]
        return len(changed)

    def unseen_count(self) -> int:
        return self.unseen_pr_count() + self.unseen_branch_count()

    def mark_all_seen(self) -> None:
        """Mark every seen-participating item seen and persist the stamps."""
        self.seen.mark_all_seen(self.integration_id, self.seen_items())
        self._save_seen()
        self.refresh()

    def selected_item(self) -> PullRequest | PushedBranch | None:
        if self.active_view is GitHubView.MENU:
            return None
        if self.active_view is GitHubView.PULL_REQUEST:
            return self.viewed
        if self.active_view is GitHubView.PUSHED_BRANCHES:
            if not self.is_mounted:
                return None
            return self._pushed_branches().selected_branch()
        if not self.is_mounted:
            return None
        return self._inbox().selected_item()

    def detail_keys_in_use(self) -> set[tuple[str, str]]:
        """The open pull request's cache key survives pruning while it is on screen."""
        keys = super().detail_keys_in_use()
        if self.viewed is not None:
            keys.add(self.detail_key(self.viewed))
        return keys

    def ready_text(self) -> str:
        if not self.is_mounted:
            return super().ready_text()
        if self.active_view is GitHubView.MENU:
            return "\n".join(self._menu().content_lines())
        if self.active_view is GitHubView.INBOX:
            return "\n".join(self._inbox().content_lines())
        if self.active_view is GitHubView.PULL_REQUEST:
            return "\n".join(self._pull_request().content_lines())
        return "\n".join(self._pushed_branches().content_lines())

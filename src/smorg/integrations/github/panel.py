"""GitHub's tab: a host panel that swaps between full views owned by this integration."""

from __future__ import annotations

from textual.app import ComposeResult

from smorg.core.contract import Item
from smorg.integrations.github.loading import GitHubLoading
from smorg.integrations.github.palette import ramp_for_background
from smorg.integrations.github.refresh import GitHubRefreshIndicator
from smorg.integrations.github.source import (
    DiffRequest,
    Profile,
    PullRequest,
    PushedBranch,
    PushedBranches,
    diff_request_of,
)
from smorg.integrations.github.views import GitHubView
from smorg.integrations.github.views.diff import GitHubDiffView
from smorg.integrations.github.views.inbox import GitHubInbox
from smorg.integrations.github.views.menu import GitHubMenu
from smorg.integrations.github.views.pull_request import GitHubPullRequestView
from smorg.integrations.github.views.pushed import GitHubPushedBranches
from smorg.shell.panel import PanelState
from smorg.shell.view_host import HostedView, ViewHostPanel

_VIEW_CLASSES: dict[GitHubView, type[HostedView]] = {
    GitHubView.MENU: GitHubMenu,
    GitHubView.INBOX: GitHubInbox,
    GitHubView.PULL_REQUEST: GitHubPullRequestView,
    GitHubView.DIFF: GitHubDiffView,
    GitHubView.PUSHED_BRANCHES: GitHubPushedBranches,
}


class GitHubPanel(ViewHostPanel[GitHubView]):
    DEFAULT_CSS = """
    GitHubPanel { align-horizontal: center; }
    """
    refresh_indicator_class = GitHubRefreshIndicator

    def __init__(self) -> None:
        super().__init__(GitHubView.MENU)
        self.viewed: PullRequest | None = None
        self.viewed_diff: DiffRequest | None = None

    def compose(self) -> ComposeResult:
        yield GitHubLoading("connecting to github", id="loading")
        yield GitHubMenu(self)
        yield GitHubInbox(self)
        yield GitHubPullRequestView(self)
        yield GitHubDiffView(self)
        yield GitHubPushedBranches(self)

    def view_classes(self) -> dict[GitHubView, type[HostedView]]:
        return _VIEW_CLASSES

    def views_shown(self) -> bool:
        return self.state is not PanelState.LOADING

    def _sync_view_display(self) -> None:
        is_loading = self.state is PanelState.LOADING
        # Focusable only during the loading takeover; at any other time it would sit in the tab
        # order as a bindingless focus stop.
        self.can_focus = is_loading
        self._loading().display = is_loading
        super()._sync_view_display()

    def show_fetch_phase(self, label: str) -> None:
        if self.state is not PanelState.LOADING or not self.is_mounted:
            return
        loading = self._loading()
        loading.reason = f"fetching {label}"
        loading.refresh()

    def open_pull_request(self, pr: PullRequest) -> None:
        """Show one pull request full screen; its detail loads while the header renders."""
        self.viewed = pr
        self.request_detail(pr)
        self.mark_seen(pr)
        self.show_view(GitHubView.PULL_REQUEST)

    def close_pull_request(self) -> None:
        self.viewed = None
        self.viewed_diff = None
        self.show_view(GitHubView.INBOX)

    def open_diff(self) -> None:
        if self.viewed is None:
            return
        request = diff_request_of(self.viewed)
        self.viewed_diff = request
        self.request_detail(request)
        self.show_view(GitHubView.DIFF)

    def close_diff(self) -> None:
        self.viewed_diff = None
        self.show_view(GitHubView.PULL_REQUEST)

    def _loading(self) -> GitHubLoading:
        return self.query_one("#loading", GitHubLoading)

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
        return ramp_for_background(self._terminal_background())

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

    def selected_item(self) -> PullRequest | PushedBranch | None:
        if self.active_view is GitHubView.MENU:
            return None
        if self.active_view in (GitHubView.PULL_REQUEST, GitHubView.DIFF):
            return self.viewed
        if self.active_view is GitHubView.PUSHED_BRANCHES:
            if not self.is_mounted:
                return None
            return self.query_one(GitHubPushedBranches).selected_branch()
        if not self.is_mounted:
            return None
        return self.query_one(GitHubInbox).selected_item()

    def detail_keys_in_use(self) -> set[tuple[str, str]]:
        """The open pull request's cache key survives pruning while it is on screen."""
        keys = super().detail_keys_in_use()
        if self.viewed is not None:
            keys.add(self.detail_key(self.viewed))
        if self.viewed_diff is not None:
            keys.add(self.detail_key(self.viewed_diff))
        return keys

"""Shared fixtures for GitHub panel/view tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from textual.app import App, ComposeResult

from smorg.core.contract import Item
from smorg.core.state import SeenState
from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.github.source import (
    PROFILE_ID,
    PUSHED_BRANCHES_ID,
    Category,
    ContributionWeek,
    Profile,
    PullRequest,
    PushedBranch,
    PushedBranches,
)
from smorg.integrations.github.views.inbox import GitHubInbox
from smorg.integrations.github.views.menu import GitHubMenu
from smorg.shell.panel import PanelState

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def pull(
    number: int = 42,
    category: Category = Category.NEEDS_YOUR_REVIEW,
    repository: str = "octocat/hello",
    title: str | None = None,
    author: str = "octocat",
) -> PullRequest:
    if title is None:
        title = f"title of #{number}"
    return PullRequest(
        id=f"{repository}#{number}",
        updated_at=NOW,
        url=f"https://github.com/{repository}/pull/{number}",
        number=number,
        title=title,
        repository=repository,
        author=author,
        category=category,
    )


def profile_item() -> Profile:
    # Two weeks, not one: a month header needs at least 4 columns to fit a full "Aug".
    weeks = (
        ContributionWeek(first_day=date(2026, 8, 9), levels=(0, 1, 2, 3, 4, 0, 0)),
        ContributionWeek(first_day=date(2026, 8, 16), levels=(1, 0, 2, 0, 3, 0, 4)),
    )
    return Profile(
        id=PROFILE_ID,
        updated_at=datetime(1970, 1, 1, tzinfo=UTC),
        url="https://github.com/octocat",
        login="octocat",
        total_contributions=204,
        weeks=weeks,
    )


def unavailable_profile_item() -> Profile:
    return Profile(
        id=PROFILE_ID,
        updated_at=datetime(1970, 1, 1, tzinfo=UTC),
        url="https://github.com",
        login="",
        total_contributions=0,
        weeks=(),
        unavailable=True,
    )


def pushed_branch(
    branch: str = "feature-branch",
    repository: str = "octocat/hello",
) -> PushedBranch:
    return PushedBranch(
        id=f"{repository}:{branch}",
        updated_at=NOW,
        url=f"https://github.com/{repository}/tree/{branch}",
        repository=repository,
        branch=branch,
        headline=f"headline of {branch}",
        compare_url=f"https://github.com/{repository}/pull/new/{branch}",
    )


def pushed_branches_item(*branches: PushedBranch) -> PushedBranches:
    return PushedBranches(
        id=PUSHED_BRANCHES_ID,
        updated_at=datetime(1970, 1, 1, tzinfo=UTC),
        url="https://github.com",
        branches=branches,
    )


def unavailable_pushed_branches_item() -> PushedBranches:
    return PushedBranches(
        id=PUSHED_BRANCHES_ID,
        updated_at=datetime(1970, 1, 1, tzinfo=UTC),
        url="https://github.com",
        branches=(),
        unavailable=True,
    )


def panel_with(*items: Item, seen: SeenState | None = None) -> GitHubPanel:
    panel = GitHubPanel()
    panel.state = PanelState.READY
    panel.items = items
    panel.seen = seen or SeenState({})
    panel.integration_id = "github"
    return panel


def inbox_with(*pulls: PullRequest, seen: SeenState | None = None) -> GitHubInbox:
    return GitHubInbox(panel_with(*pulls, seen=seen))


def menu_with(*items: Item, seen: SeenState | None = None) -> GitHubMenu:
    return GitHubMenu(panel_with(*items, seen=seen))


class PanelHarness(App[None]):
    """The smallest app that can mount a `GitHubPanel` and hand it focus."""

    def __init__(self, panel: GitHubPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel

    def on_mount(self) -> None:
        self._panel.focus()

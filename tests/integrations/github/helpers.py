"""Shared fixtures for GitHub panel/view tests."""

from __future__ import annotations

from datetime import UTC, datetime

from textual.app import App, ComposeResult

from smorg.core.contract import Item
from smorg.core.state import SeenState
from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.github.source import PROFILE_ID, Category, Profile, PullRequest
from smorg.integrations.github.views.inbox import GitHubInbox
from smorg.integrations.github.views.menu import GitHubMenu
from smorg.shell.panel import PanelState

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def pull(
    number: int = 42,
    category: Category = Category.NEEDS_YOUR_REVIEW,
    repository: str = "octocat/hello",
    title: str | None = None,
) -> PullRequest:
    return PullRequest(
        id=f"{repository}#{number}",
        updated_at=NOW,
        url=f"https://github.com/{repository}/pull/{number}",
        number=number,
        title=title if title is not None else f"title of #{number}",
        repository=repository,
        author="octocat",
        category=category,
    )


def profile_item() -> Profile:
    return Profile(
        id=PROFILE_ID,
        updated_at=datetime(1970, 1, 1, tzinfo=UTC),
        url="https://github.com",
        login="octocat",
        total_contributions=204,
        weeks=((0, 1, 2, 3, 4, 0, 0),),
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

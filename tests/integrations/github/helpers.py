"""Shared fixtures for GitHub panel/view tests."""

from __future__ import annotations

from datetime import UTC, datetime

from smorg.core.state import SeenState
from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.github.source import Category, PullRequest
from smorg.integrations.github.views.inbox import GitHubInbox
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


def panel_with(*pulls: PullRequest, seen: SeenState | None = None) -> GitHubPanel:
    panel = GitHubPanel()
    panel.state = PanelState.READY
    panel.items = pulls
    panel.seen = seen or SeenState({})
    panel.integration_id = "github"
    return panel


def inbox_with(*pulls: PullRequest, seen: SeenState | None = None) -> GitHubInbox:
    return GitHubInbox(panel_with(*pulls, seen=seen))

"""Tests for the GitHub loading view: the octocat, the bouncing bar, and its lifecycle."""

from __future__ import annotations

import io

from rich.console import Console

from smorg.integrations.github.loading import _SEGMENT_WIDTH, _TRACK_WIDTH, GitHubLoading
from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.github.views.menu import GitHubMenu
from smorg.shell.panel import PanelState

from .helpers import PanelHarness, profile_item


async def test_loading_shows_only_while_the_panel_loads():
    panel = GitHubPanel()
    panel.integration_id = "github"
    async with PanelHarness(panel).run_test() as pilot:
        assert panel.query_one(GitHubLoading).display is True
        assert panel.query_one(GitHubMenu).display is False
        panel.state = PanelState.READY
        panel.items = (profile_item(),)
        panel.refresh()
        await pilot.pause()
        assert panel.query_one(GitHubLoading).display is False
        assert panel.query_one(GitHubMenu).display is True
        assert panel.app.focused is panel.query_one(GitHubMenu)


async def test_the_animation_runs_only_while_shown():
    panel = GitHubPanel()
    panel.integration_id = "github"
    async with PanelHarness(panel).run_test() as pilot:
        loading = panel.query_one(GitHubLoading)
        await pilot.pause()
        assert loading.is_animating is True
        panel.state = PanelState.READY
        panel.refresh()
        await pilot.pause()
        assert loading.is_animating is False


def test_the_bar_bounces_between_the_track_ends():
    loading = GitHubLoading("loading your pull requests")
    positions = []
    for _ in range(2 * (_TRACK_WIDTH - _SEGMENT_WIDTH) + 2):
        loading._advance()
        positions.append(loading.bar_position)
    assert max(positions) == _TRACK_WIDTH - _SEGMENT_WIDTH
    assert min(positions) == 0


def test_the_widget_says_what_it_loads():
    loading = GitHubLoading("loading the pull request")

    console = Console(width=60, file=io.StringIO(), force_terminal=False)
    with console.capture() as capture:
        console.print(loading.render())

    assert "loading the pull request" in capture.get()

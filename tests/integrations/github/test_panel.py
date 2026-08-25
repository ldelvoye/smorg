"""Tests for the GitHub host panel: view delegation, never the network."""

import json
from pathlib import Path

from smorg.core.state import SeenState
from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.github.source import (
    PROFILE_ID,
    UNAVAILABLE_CHECKS,
    Category,
    LineCounts,
    Newest,
    PullRequestDetail,
)
from smorg.integrations.github.views import GitHubView
from smorg.integrations.github.views.inbox import GitHubInbox
from smorg.integrations.github.views.menu import GitHubMenu
from smorg.integrations.github.views.pull_request import GitHubPullRequestView
from smorg.shell.panel import ScrollGutter

from .helpers import PanelHarness, panel_with, profile_item, pull


def test_the_panel_and_its_views_never_fetch():
    """The seam the whole design rests on, enforced rather than trusted."""
    github_dir = Path("src") / "smorg" / "integrations" / "github"
    files = [github_dir / "panel.py", github_dir / "loading.py"] + sorted(
        github_dir.glob("views/*.py")
    )
    for file in files:
        source = file.read_text()
        assert "httpx" not in source, file
        assert "Github(" not in source, file
        assert "import requests" not in source, file
        assert "fetch" not in source, file
        assert "shell.app" not in source, file


def test_an_unmounted_host_has_no_selection():
    assert panel_with(pull(42)).selected_item() is None


def test_mark_all_seen_only_stores_pull_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    seen = SeenState({})
    panel = panel_with(pull(42), seen=seen)
    panel.mark_all_seen()
    assert not seen.is_changed("github", pull(42))


def test_mark_all_seen_never_stores_the_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    seen = SeenState({})
    panel = panel_with(pull(42), seen=seen)
    panel.items = panel.items + (profile_item(),)
    panel.mark_all_seen()
    assert not seen.is_changed("github", pull(42))
    saved = json.loads((tmp_path / "state.json").read_text())
    assert PROFILE_ID not in saved.get("github", {})


# --- Menu, the initial view, and navigation to the inbox ---


def test_the_tab_opens_on_the_menu():
    assert panel_with().active_view is GitHubView.MENU


def test_help_bindings_follow_the_active_view():
    panel = panel_with(pull(42))
    assert list(panel.help_bindings()) == list(GitHubMenu.BINDINGS)
    panel.active_view = GitHubView.INBOX
    assert list(panel.help_bindings()) == list(GitHubInbox.BINDINGS)
    panel.active_view = GitHubView.PULL_REQUEST
    assert list(panel.help_bindings()) == list(GitHubPullRequestView.BINDINGS)


def test_the_menu_view_has_no_selection_for_mark_unseen():
    panel = panel_with(pull(42))
    assert panel.selected_item() is None


async def test_enter_opens_the_inbox_and_escape_returns():
    panel = panel_with(profile_item(), pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        assert panel.query_one(GitHubMenu).display is True
        assert panel.query_one(GitHubInbox).display is False

        await pilot.press("enter")

        assert panel.active_view is GitHubView.INBOX
        assert panel.query_one(GitHubInbox).display is True
        assert panel.query_one(GitHubMenu).display is False

        await pilot.press("escape")

        assert panel.active_view is GitHubView.MENU
        assert panel.query_one(GitHubMenu).display is True


# --- The host in a mounted tree ---


async def test_a_mounted_host_forwards_focus_and_keys_to_the_inbox():
    panel = panel_with(pull(42), pull(43, Category.NEEDS_TEAM_REVIEW))
    async with PanelHarness(panel).run_test() as pilot:
        panel.show_view(GitHubView.INBOX)
        await pilot.pause()

        inbox = panel.query_one(GitHubInbox)
        assert panel.app.focused is inbox

        before = panel.selected_item()
        await pilot.press("down")

        assert panel.selected_item() is not before


async def test_the_host_is_not_a_focus_stop():
    """A focusable host with no bindings of its own would swallow the tab key."""
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        await pilot.press("tab")

        assert panel.app.focused is not panel


async def test_the_tab_has_no_detail_region_and_still_refreshes():
    """The pane left this tab; the shell's guarded display half must shrug, not crash."""
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test():
        assert panel.query_one("#body") is not None
        assert not panel.query("#detail")
        panel.refresh()


async def test_enter_opens_the_pull_request_view_and_escape_returns(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        panel.show_view(GitHubView.INBOX)
        await pilot.pause()

        await pilot.press("enter")

        assert panel.active_view is GitHubView.PULL_REQUEST
        assert panel.viewed is not None and panel.viewed.number == 42
        assert panel.query_one(GitHubPullRequestView).display is True

        await pilot.press("escape")

        assert panel.active_view is GitHubView.INBOX
        assert panel.viewed is None


async def test_opening_a_pull_request_marks_it_seen(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    seen = SeenState({})
    panel = panel_with(pull(42), seen=seen)
    async with PanelHarness(panel).run_test() as pilot:
        panel.show_view(GitHubView.INBOX)
        await pilot.pause()

        await pilot.press("enter")

        assert not seen.is_changed("github", pull(42))


async def test_a_refresh_cannot_steal_the_viewed_pull_request(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        panel.show_view(GitHubView.INBOX)
        await pilot.pause()
        await pilot.press("enter")

        panel.items = (pull(51, Category.DRAFT),)
        panel.refresh()

        assert panel.active_view is GitHubView.PULL_REQUEST
        assert panel.viewed is not None and panel.viewed.number == 42


def test_pruning_protects_the_viewed_pull_requests_detail():
    panel = panel_with()
    panel.viewed = pull(42)
    panel.show_detail(GitHubPanel.detail_key(panel.viewed), object())

    panel.prune_detail_cache()

    assert panel.detail_for(panel.viewed) is not None


async def test_the_view_scrolls_behind_the_gutter_not_a_scrollbar(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        panel.show_view(GitHubView.INBOX)
        await pilot.pause()
        await pilot.press("enter")

        view = panel.query_one(GitHubPullRequestView)
        assert view.query(ScrollGutter)
        assert view.styles.scrollbar_size_vertical == 0


async def test_the_gutter_shows_the_down_arrow_before_any_scroll(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        panel.show_view(GitHubView.INBOX)
        await pilot.pause()
        await pilot.press("enter")

        long_body = "\n\n".join(f"paragraph {index}" for index in range(80))
        shown = PullRequestDetail(
            body=long_body,
            base="main",
            head="tall",
            reviewers=(),
            reviews=Newest(items=()),
            comments=Newest(items=()),
            counts=LineCounts(),
            checks=UNAVAILABLE_CHECKS,
        )
        panel.show_detail(GitHubPanel.detail_key(pull(42)), shown)
        await pilot.pause()

        gutter = panel.query_one(GitHubPullRequestView).query_one(ScrollGutter)
        assert "↓" in str(gutter.content)

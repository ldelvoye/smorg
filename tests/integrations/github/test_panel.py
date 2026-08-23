"""Tests for the GitHub host panel: view delegation, never the network."""

import json
from pathlib import Path

from smorg.core.state import SeenState
from smorg.integrations.github.source import PROFILE_ID, Category
from smorg.integrations.github.views import GitHubView
from smorg.integrations.github.views.inbox import GitHubInbox
from smorg.integrations.github.views.menu import GitHubMenu

from .helpers import PanelHarness, panel_with, profile_item, pull


def test_the_panel_and_its_views_never_fetch():
    """The seam the whole design rests on, enforced rather than trusted."""
    github_dir = Path("src") / "smorg" / "integrations" / "github"
    files = [github_dir / "panel.py"] + sorted(github_dir.glob("views/*.py"))
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


async def test_base_panel_machinery_resolves_through_the_inbox():
    """`Panel`'s own descendant queries for #body/#detail must still find them one
    level deeper, inside the inbox.
    """
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test():
        assert panel.query_one("#body") is not None
        assert panel.query_one("#detail") is not None

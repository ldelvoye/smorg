"""Tests for the GitHub host panel: view delegation, never the network."""

from pathlib import Path

from smorg.core.state import SeenState
from smorg.integrations.github.source import Category
from smorg.integrations.github.views.inbox import GitHubInbox

from .helpers import PanelHarness, panel_with, pull


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


# --- The host in a mounted tree ---


async def test_a_mounted_host_forwards_focus_and_keys_to_the_inbox():
    panel = panel_with(pull(42), pull(43, Category.NEEDS_TEAM_REVIEW))
    async with PanelHarness(panel).run_test() as pilot:
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

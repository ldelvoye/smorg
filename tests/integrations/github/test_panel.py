"""Tests for the GitHub host panel: view delegation, never the network."""

import json
from pathlib import Path

from smorg.core.contract import Newest
from smorg.core.state import SeenState
from smorg.integrations.github.loading import GitHubLoading
from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.github.source import (
    PROFILE_ID,
    UNAVAILABLE_CHECKS,
    Category,
    FileDiff,
    LineCounts,
    PullRequestDetail,
    PullRequestDiff,
)
from smorg.integrations.github.views import GitHubView
from smorg.integrations.github.views.diff import GitHubDiffView
from smorg.integrations.github.views.inbox import GitHubInbox
from smorg.integrations.github.views.menu import GitHubMenu
from smorg.integrations.github.views.pull_request import GitHubPullRequestView
from smorg.integrations.github.views.pushed import GitHubPushedBranches
from smorg.shell.panel import ScrollGutter

from .helpers import (
    PanelHarness,
    panel_with,
    profile_item,
    pull,
    pushed_branch,
    pushed_branches_item,
)


def detail_with(**overrides) -> PullRequestDetail:
    fields = {
        "body": "",
        "base": "main",
        "head": "tall",
        "reviewers": (),
        "comments": Newest(items=()),
        "counts": LineCounts(),
        "checks": UNAVAILABLE_CHECKS,
    }
    return PullRequestDetail(**(fields | overrides))


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
        # show_fetch_phase and its caption are display-only; drop them before the fetch trip-wire.
        scrubbed = source.replace("show_fetch_phase", "").replace("fetching", "")
        assert "fetch" not in scrubbed, file
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


def test_mark_all_seen_also_stores_pushed_branches(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    seen = SeenState({})
    branch = pushed_branch()
    panel = panel_with(pull(42), pushed_branches_item(branch), seen=seen)
    panel.mark_all_seen()
    assert not seen.is_changed("github", pull(42))
    assert not seen.is_changed("github", branch)


def test_unseen_count_sums_pull_requests_and_pushed_branches():
    seen = SeenState({})
    branch = pushed_branch()
    panel = panel_with(pull(42), pushed_branches_item(branch), seen=seen)
    assert panel.unseen_pr_count() == 1
    assert panel.unseen_branch_count() == 1
    assert panel.unseen_count() == 2


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
    panel.active_view = GitHubView.PUSHED_BRANCHES
    assert list(panel.help_bindings()) == list(GitHubPushedBranches.BINDINGS)


def test_the_menu_view_has_no_selection_for_mark_unseen():
    panel = panel_with(pull(42))
    assert panel.selected_item() is None


async def test_mark_unseen_restores_a_pushed_branchs_changed_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    seen = SeenState({})
    branch = pushed_branch()
    panel = panel_with(pushed_branches_item(branch), seen=seen)
    panel.active_view = GitHubView.PUSHED_BRANCHES
    async with PanelHarness(panel).run_test():
        panel.mark_seen(branch)
        assert not seen.is_changed("github", branch)

        panel.mark_unseen()

        assert seen.is_changed("github", branch)


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


async def open_pull_request(pilot, panel: GitHubPanel) -> None:
    """Show the inbox, then press enter to open its first pull request."""
    panel.show_view(GitHubView.INBOX)
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


async def test_enter_opens_the_pull_request_view_and_escape_returns(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        await open_pull_request(pilot, panel)

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
        await open_pull_request(pilot, panel)

        assert not seen.is_changed("github", pull(42))


async def test_a_refresh_cannot_steal_the_viewed_pull_request(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        await open_pull_request(pilot, panel)

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
        await open_pull_request(pilot, panel)

        view = panel.query_one(GitHubPullRequestView)
        assert view.query(ScrollGutter)
        assert view.styles.scrollbar_size_vertical == 0


async def test_the_gutter_shows_the_down_arrow_before_any_scroll(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        await open_pull_request(pilot, panel)

        long_body = "\n\n".join(f"paragraph {index}" for index in range(80))
        shown = detail_with(body=long_body)
        panel.show_detail(GitHubPanel.detail_key(pull(42)), shown)
        await pilot.pause()
        await pilot.pause()

        gutter = panel.query_one(GitHubPullRequestView).query_one(ScrollGutter)
        assert "↓" in str(gutter.content)


async def test_opening_a_pull_request_shows_the_octocat_until_detail_lands(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        await open_pull_request(pilot, panel)

        view = panel.query_one(GitHubPullRequestView)
        assert view.query_one(GitHubLoading).display is True
        assert view.query_one("#pull-request-body").display is False

        shown = detail_with(body="hello")
        panel.show_detail(GitHubPanel.detail_key(pull(42)), shown)
        await pilot.pause()

        assert view.query_one(GitHubLoading).display is False
        assert view.query_one("#pull-request-body").display is True


async def test_escape_still_works_while_the_detail_loads(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        await open_pull_request(pilot, panel)

        await pilot.press("escape")

        assert panel.active_view is GitHubView.INBOX


# --- The diff view ---


def file_diff(path: str) -> FileDiff:
    return FileDiff(path=path, previous_path="", additions=1, deletions=0, patch="+x")


async def test_enter_opens_the_diff_view_and_j_k_clamp_the_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    panel = panel_with(pull(42))
    async with PanelHarness(panel).run_test() as pilot:
        await open_pull_request(pilot, panel)

        await pilot.press("enter")
        await pilot.pause()
        assert panel.active_view is GitHubView.DIFF
        assert panel.viewed_diff is not None

        files = (file_diff("a.py"), file_diff("b.py"), file_diff("c.py"))
        diff = PullRequestDiff(files=files, truncated=False)
        panel.show_detail(panel.detail_key(panel.viewed_diff), diff)
        await pilot.pause()

        view = panel.query_one(GitHubDiffView)
        assert view.selected_index == 0

        for _ in range(4):
            await pilot.press("j")
        await pilot.pause()
        assert view.selected_index == 2

        for _ in range(4):
            await pilot.press("k")
        await pilot.pause()
        assert view.selected_index == 0

        await pilot.press("escape")
        await pilot.pause()
        assert panel.active_view is GitHubView.PULL_REQUEST


# --- Theme-aware status colors, without a mounted app ---


def test_status_colors_default_to_the_dark_shades_without_an_app():
    colors = panel_with().status_colors()

    assert colors.red == "#f85149"

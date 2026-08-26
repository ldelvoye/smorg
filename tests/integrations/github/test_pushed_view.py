"""Tests for the GitHub pushed-branches view: one card, one flat cursor."""

from __future__ import annotations

import pytest

from smorg.core.state import SeenState
from smorg.integrations.github.views import GitHubView
from smorg.integrations.github.views.pushed import GitHubPushedBranches

from .helpers import (
    PanelHarness,
    panel_with,
    pushed_branch,
    pushed_branches_item,
    unavailable_pushed_branches_item,
)

# --- Render states ---


def test_a_ready_container_renders_branch_rows_and_the_card_title():
    first = pushed_branch("feature-one")
    second = pushed_branch("feature-two")
    view = GitHubPushedBranches(panel_with(pushed_branches_item(first, second)))

    text = "\n".join(view.content_lines())

    assert "feature-one" in text
    assert "feature-two" in text
    assert "pushed branches (2)" in text


def test_an_empty_container_reads_nothing_recently_pushed():
    view = GitHubPushedBranches(panel_with(pushed_branches_item()))

    text = "\n".join(view.content_lines())

    assert "nothing recently pushed" in text


@pytest.mark.parametrize(
    "container",
    [unavailable_pushed_branches_item(), None],
    ids=["unavailable", "absent"],
)
def test_unavailable_or_absent_reads_the_same_line(container):
    items = () if container is None else (container,)
    view = GitHubPushedBranches(panel_with(*items))

    text = "\n".join(view.content_lines())

    assert "pushed branches unavailable with this token" in text


# --- Selection and changed marks ---


def test_only_the_selected_row_carries_the_marker():
    first = pushed_branch("feature-one")
    second = pushed_branch("feature-two")
    view = GitHubPushedBranches(panel_with(pushed_branches_item(first, second)))

    lines = view.content_lines()
    marked = [line for line in lines if "▸" in line]

    assert len(marked) == 1
    assert "feature-one" in marked[0]


def test_an_unseen_branch_is_marked_and_a_seen_one_is_not():
    seen = SeenState({})
    changed = pushed_branch("feature-one")
    unchanged = pushed_branch("feature-two")
    seen.mark_seen("github", unchanged)
    view = GitHubPushedBranches(panel_with(pushed_branches_item(changed, unchanged), seen=seen))

    lines = view.content_lines()
    marked = [line for line in lines if "●" in line]

    assert any("feature-one" in line for line in marked)
    assert not any("feature-two" in line for line in marked)


# --- Cursor ---


def test_the_cursor_wraps_both_directions():
    first = pushed_branch("feature-one")
    second = pushed_branch("feature-two")
    view = GitHubPushedBranches(panel_with(pushed_branches_item(first, second)))

    assert view.selected_branch() is first

    view.action_cursor_down()
    assert view.selected_branch() is second

    view.action_cursor_down()
    assert view.selected_branch() is first

    view.action_cursor_up()
    assert view.selected_branch() is second


def test_the_cursor_clamps_when_the_branch_list_shrinks():
    first = pushed_branch("feature-one")
    second = pushed_branch("feature-two")
    panel = panel_with(pushed_branches_item(first, second))
    view = GitHubPushedBranches(panel)
    view.action_cursor_down()

    panel.items = (pushed_branches_item(first),)

    assert view.selected_branch() is first


# --- Opening a branch's create-PR page ---


def test_open_selected_opens_the_compare_url_and_marks_seen(monkeypatch, tmp_path):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    opened: list[str] = []
    monkeypatch.setattr(
        "smorg.integrations.github.views.pushed.webbrowser.open", lambda url: opened.append(url)
    )
    seen = SeenState({})
    branch = pushed_branch()
    view = GitHubPushedBranches(panel_with(pushed_branches_item(branch), seen=seen))

    view.action_open_selected()

    assert opened == [branch.compare_url]
    assert not seen.is_changed("github", branch)


def test_open_selected_is_a_no_op_with_no_branches(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "smorg.integrations.github.views.pushed.webbrowser.open", lambda url: opened.append(url)
    )
    view = GitHubPushedBranches(panel_with(pushed_branches_item()))

    view.action_open_selected()

    assert opened == []


# --- Getting back to the menu ---


async def test_back_to_menu_returns_to_the_menu_view():
    panel = panel_with(pushed_branches_item(pushed_branch()))
    async with PanelHarness(panel).run_test() as pilot:
        panel.show_view(GitHubView.PUSHED_BRANCHES)
        await pilot.pause()

        view = panel.query_one(GitHubPushedBranches)
        view.action_back_to_menu()

        assert panel.active_view is GitHubView.MENU

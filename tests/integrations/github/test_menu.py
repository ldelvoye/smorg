"""Tests for the GitHub menu: welcome line, updates line, and the destination list."""

from __future__ import annotations

from datetime import date

from smorg.core.state import SeenState
from smorg.integrations.github.palette import (
    _GREEN_RAMP_DARK,
    _GREEN_RAMP_LIGHT,
    ramp_for_background,
)
from smorg.integrations.github.source import ABSENT_DAY, Category, ContributionWeek
from smorg.integrations.github.views import GitHubView
from smorg.integrations.github.views.menu import (
    _GUTTER_WIDTH,
    GitHubMenu,
    _fit_weeks,
    _format_graph_rows,
    _format_month_header,
)
from smorg.integrations.github.views.pushed import GitHubPushedBranches

from .helpers import (
    PanelHarness,
    menu_with,
    panel_with,
    profile_item,
    pull,
    pushed_branch,
    pushed_branches_item,
    unavailable_profile_item,
)


def menu_text(menu: GitHubMenu) -> str:
    return "\n".join(menu.content_lines())


def test_the_welcome_line_names_the_signed_in_user():
    menu = menu_with(profile_item())
    assert "welcome back, octocat" in menu_text(menu)


def test_an_unavailable_profile_still_welcomes():
    menu = menu_with(unavailable_profile_item())
    assert "welcome back" in menu_text(menu)
    assert "octocat" not in menu_text(menu)


def test_the_updates_line_counts_changed_pull_requests():
    seen = SeenState({})
    old = pull(7)
    seen.mark_seen("github", old)
    menu = menu_with(profile_item(), pull(42), old, seen=seen)
    assert "1 update since you last looked" in menu_text(menu)


def test_two_changed_pull_requests_read_as_a_plural():
    menu = menu_with(profile_item(), pull(42), pull(43, Category.NEEDS_TEAM_REVIEW))
    assert "2 updates since you last looked" in menu_text(menu)


def test_nothing_changed_reads_as_caught_up():
    seen = SeenState({})
    only = pull(42)
    seen.mark_seen("github", only)
    menu = menu_with(profile_item(), only, seen=seen)
    assert "you're all caught up" in menu_text(menu)


def test_the_pull_requests_destination_is_listed_and_selected():
    menu = menu_with(profile_item())
    lines = menu.content_lines()
    assert any("▸ pull requests" in line for line in lines)
    assert any("⏎ to open" in line for line in lines)


# --- The pushed branches destination ---


def test_the_pushed_branches_destination_is_listed_with_its_description():
    lines = menu_with(profile_item()).content_lines()

    assert any("pushed branches" in line for line in lines)
    assert any("recent pushes to branches with no pull request yet" in line for line in lines)


def test_the_badge_shows_unseen_pushed_branches_and_hides_once_seen():
    seen = SeenState({})
    branch = pushed_branch()
    unseen_text = "\n".join(
        menu_with(profile_item(), pushed_branches_item(branch), seen=seen).content_lines()
    )
    assert "● 1 update" in unseen_text

    seen.mark_seen("github", branch)
    seen_text = "\n".join(
        menu_with(profile_item(), pushed_branches_item(branch), seen=seen).content_lines()
    )
    assert "● 1 update" not in seen_text


async def test_cursor_navigation_reaches_pushed_branches_and_opening_it_shows_the_view():
    panel = panel_with(profile_item())
    async with PanelHarness(panel).run_test() as pilot:
        menu = panel.query_one(GitHubMenu)
        assert menu.destination_cursor == 0

        menu.action_next_destination()

        assert menu.destination_cursor == 1

        menu.action_open_destination()
        await pilot.pause()

        assert panel.active_view is GitHubView.PUSHED_BRANCHES
        assert panel.query_one(GitHubPushedBranches).display is True


# --- Opening the signed-in user's GitHub profile ---


def test_pressing_o_opens_the_signed_in_users_profile(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "smorg.integrations.github.views.menu.webbrowser.open", lambda url: opened.append(url)
    )
    menu = menu_with(profile_item())

    menu.action_open_profile()

    assert opened == ["https://github.com/octocat"]


def test_opening_the_profile_is_a_no_op_without_one(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "smorg.integrations.github.views.menu.webbrowser.open", lambda url: opened.append(url)
    )
    menu = menu_with()

    menu.action_open_profile()

    assert opened == []


# --- The contribution graph card ---

RAMP = ("#006d32", "#26a641", "#39d353", "#7ee787")
WEEK_START = date(2026, 8, 9)


def test_levels_map_to_glyphs_and_ramp_colors():
    week = ContributionWeek(first_day=WEEK_START, levels=(0, 1, 2, 3, 4, 0, ABSENT_DAY))
    rows = _format_graph_rows((week,), RAMP)
    assert len(rows) == 7
    assert rows[0].plain[_GUTTER_WIDTH:].strip() == "·"  # level 0: dim dot
    assert rows[1].plain[_GUTTER_WIDTH:].strip() == "▄"  # level 1+: block
    assert str(rows[1].spans[1].style) == RAMP[0]
    assert str(rows[2].spans[1].style) == RAMP[1]
    assert str(rows[3].spans[1].style) == RAMP[2]
    assert str(rows[4].spans[1].style) == RAMP[3]
    assert rows[6].plain[_GUTTER_WIDTH:].strip() == ""  # absent day: blank


def test_only_trailing_weeks_that_fit_are_shown():
    weeks = tuple(
        ContributionWeek(first_day=WEEK_START, levels=(index % 5, 0, 0, 0, 0, 0, 0))
        for index in range(53)
    )
    fitted = _fit_weeks(weeks, available_width=20)
    assert len(fitted) == 10  # 2 cells per week column
    assert fitted == weeks[-10:]


def test_the_card_carries_the_contribution_count():
    menu = menu_with(profile_item())
    assert "204 contributions in the last year" in "\n".join(menu.content_lines())


def test_the_card_shows_day_and_month_labels():
    menu = menu_with(profile_item())
    text = "\n".join(menu.content_lines())
    assert "Mon" in text
    assert "Wed" in text
    assert "Fri" in text
    assert "Aug" in text  # profile_item's fixture week starts August 9th


def test_an_unavailable_profile_replaces_the_card_with_one_line():
    menu = menu_with(unavailable_profile_item())
    text = "\n".join(menu.content_lines())
    assert "contribution graph unavailable with this token" in text
    assert "contributions in the last year" not in text


def test_a_second_month_start_within_the_gap_is_skipped():
    weeks = (
        ContributionWeek(first_day=date(2026, 7, 26), levels=(0,) * 7),
        ContributionWeek(first_day=date(2026, 8, 2), levels=(0,) * 7),
    )
    header = _format_month_header(weeks)
    assert "Jul" in header.plain
    assert "Aug" not in header.plain


def test_a_month_label_that_would_clip_is_absent_not_truncated():
    weeks = (
        ContributionWeek(first_day=date(2026, 7, 5), levels=(0,) * 7),
        ContributionWeek(first_day=date(2026, 7, 12), levels=(0,) * 7),
        ContributionWeek(first_day=date(2026, 8, 2), levels=(0,) * 7),
    )
    header = _format_month_header(weeks)
    assert "Jul" in header.plain
    assert "Aug" not in header.plain
    assert "Au" not in header.plain


def test_the_ramp_follows_the_terminal_background():
    dark = panel_with(profile_item())
    assert dark.green_ramp() == _GREEN_RAMP_DARK  # no app palette -> dark fallback


def test_a_light_background_picks_the_light_ramp():
    assert ramp_for_background((250, 250, 250)) == _GREEN_RAMP_LIGHT
    assert ramp_for_background((10, 10, 10)) == _GREEN_RAMP_DARK
    assert ramp_for_background(None) == _GREEN_RAMP_DARK

"""Tests for the GitHub menu: welcome line, updates line, and the destination list."""

from __future__ import annotations

from smorg.core.state import SeenState
from smorg.integrations.github.source import Category
from smorg.integrations.github.views.menu import GitHubMenu

from .helpers import menu_with, profile_item, pull, unavailable_profile_item


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


def test_the_inbox_destination_is_listed_and_selected():
    menu = menu_with(profile_item())
    lines = menu.content_lines()
    assert any("▸ inbox" in line for line in lines)

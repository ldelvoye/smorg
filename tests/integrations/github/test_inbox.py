"""Tests for the GitHub inbox: two columns, a cursor in each, and no network."""

import io
from datetime import UTC, datetime

import pytest
from rich.console import Console
from rich.text import Text

from smorg.core.state import SeenState
from smorg.integrations.github.source import (
    Category,
    PullRequest,
    PullRequestDetail,
    Review,
)
from smorg.integrations.github.views.inbox import _COLUMNS, GitHubInbox

from .helpers import inbox_with, pull

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)

LEFT_TITLE, LEFT_CATEGORIES = _COLUMNS[0]
RIGHT_TITLE, RIGHT_CATEGORIES = _COLUMNS[1]


def rendered(inbox: GitHubInbox, width: int = 100) -> str:
    console = Console(width=width, file=io.StringIO(), force_terminal=False)
    with console.capture() as capture:
        console.print(inbox.render_content())
    return capture.get()


# --- Getting back to the menu ---


def test_the_inbox_says_how_to_get_back():
    assert "‹ esc — menu" in "\n".join(inbox_with(pull(42)).content_lines())


# --- Two columns, side by side ---


def test_both_column_titles_land_on_the_same_line():
    """The whole point of the layout: the review inbox and your own pull
    requests are read side by side, not one after the other."""
    inbox = inbox_with(pull(), pull(51, Category.DRAFT))

    first_line = rendered(inbox).splitlines()[0]

    assert LEFT_TITLE in first_line
    assert RIGHT_TITLE in first_line


def test_every_declared_category_gets_a_heading():
    text = "\n".join(inbox_with(pull()).content_lines())

    for _, categories in _COLUMNS:
        for category in categories:
            assert str(category) in text


def test_an_empty_category_still_shows_its_heading_and_a_count_of_zero():
    """A section that vanishes when empty and a section that was never
    fetched look identical; a heading reading (0) says which this is."""
    text = "\n".join(inbox_with(pull()).content_lines())

    assert f"{Category.READY_TO_MERGE} (0)" in text
    assert f"{Category.NEEDS_YOUR_REVIEW} (1)" in text


def test_a_pull_request_is_drawn_under_the_category_the_source_gave_it():
    text = "\n".join(inbox_with(pull(51, Category.DRAFT)).content_lines())
    lines = text.splitlines()
    heading = lines.index(f"{Category.DRAFT} (1)")

    assert "#51" in lines[heading + 1]


def test_a_row_names_the_repository_and_the_number():
    """A review inbox spans repositories, so a bare number identifies nothing."""
    text = "\n".join(inbox_with(pull(7, repository="octocat/tools")).content_lines())

    assert "octocat/tools#7" in text


# --- Change marks ---


def test_a_changed_pull_request_is_marked_and_a_seen_one_is_not():
    seen = SeenState({})
    unchanged = pull(7, repository="octocat/tools")
    seen.mark_seen("github", unchanged)

    text = "\n".join(inbox_with(pull(42), unchanged, seen=seen).content_lines())
    marked = [line for line in text.splitlines() if "●" in line]

    assert any("#42" in line for line in marked)
    assert not any("#7" in line for line in marked)


# --- Selection moves within a column, and between them ---


def test_the_selection_starts_in_the_review_inbox():
    inbox = inbox_with(pull(42), pull(51, Category.DRAFT))

    selected = inbox.selected_item()

    assert selected is not None
    assert selected.number == 42


def test_up_and_down_move_within_the_focused_column_only():
    inbox = inbox_with(
        pull(42, Category.NEEDS_YOUR_REVIEW),
        pull(43, Category.NEEDS_TEAM_REVIEW),
        pull(51, Category.DRAFT),
    )

    inbox.action_cursor_down()
    first = inbox.selected_item()

    inbox.action_cursor_down()
    second = inbox.selected_item()

    assert first is not None and first.number == 43
    # Wraps inside the column rather than crossing into the other one.
    assert second is not None and second.number == 42


def test_right_moves_the_selection_into_your_own_pull_requests():
    inbox = inbox_with(pull(42), pull(51, Category.DRAFT))

    inbox.action_next_column()
    selected = inbox.selected_item()

    assert selected is not None
    assert selected.number == 51


def test_each_column_keeps_its_own_cursor():
    """Switching away and back returns to the row you left, not to the top."""
    inbox = inbox_with(
        pull(42, Category.NEEDS_YOUR_REVIEW),
        pull(43, Category.NEEDS_TEAM_REVIEW),
        pull(51, Category.DRAFT),
    )
    inbox.action_cursor_down()

    inbox.action_next_column()
    inbox.action_previous_column()
    selected = inbox.selected_item()

    assert selected is not None
    assert selected.number == 43


def test_an_empty_column_has_nothing_selected_and_moving_is_a_no_op():
    inbox = inbox_with(pull(42))

    inbox.action_next_column()
    inbox.action_cursor_down()

    assert inbox.selected_item() is None
    assert inbox.selected_url() is None


def test_the_open_action_returns_the_url_of_the_selected_pull_request():
    inbox = inbox_with(pull(42), pull(51, Category.DRAFT))
    inbox.action_next_column()

    assert inbox.selected_url() == "https://github.com/octocat/hello/pull/51"


# --- Server text cannot restyle the inbox ---


def test_a_title_that_looks_like_markup_is_drawn_literally():
    """Rich markup in a title would otherwise let somebody else's pull request
    colour or hide rows in your dashboard."""
    inbox = inbox_with(pull(42, title="[red]danger[/red]"))

    assert "[red]danger[/red]" in "\n".join(inbox.content_lines())


@pytest.mark.parametrize("width", [40, 60, 120])
def test_no_row_wraps_at_any_width(width):
    """A wrapped title spills into the next row's place and breaks a grid that
    is already only half the screen wide."""
    inbox = inbox_with(pull(42, title="a very long title " * 12))

    lines = rendered(inbox, width=width).splitlines()

    assert all(len(line.rstrip()) <= width for line in lines)


# --- The detail pane ---


def detail(**overrides) -> PullRequestDetail:
    fields = {
        "body": "Splits the loader in two.",
        "base": "main",
        "head": "tidy-loader",
        "reviews": (Review(author="hubot", state="CHANGES_REQUESTED", submitted_at=NOW),),
    }
    return PullRequestDetail(**(fields | overrides))


def plain(inbox: GitHubInbox, item: PullRequest, shown: PullRequestDetail) -> str:
    console = Console(width=100, file=io.StringIO(), force_terminal=False)
    with console.capture() as capture:
        console.print(inbox.render_detail(item, shown))
    return capture.get()


def test_the_detail_names_the_pull_request_its_branches_and_its_reviews():
    item = pull(42)
    text = plain(inbox_with(item), item, detail())

    assert "octocat/hello#42" in text
    assert "tidy-loader" in text
    assert "main" in text
    assert "hubot" in text


def test_a_review_state_reads_as_words():
    item = pull(42)
    text = plain(inbox_with(item), item, detail())

    assert "changes requested" in text


def test_a_pull_request_with_no_description_says_so():
    """Empty and unloaded look identical otherwise."""
    item = pull(42)
    text = plain(inbox_with(item), item, detail(body=""))

    assert "no description" in text


def test_dropped_reviews_are_counted_rather_than_silently_missing():
    item = pull(42)
    text = plain(inbox_with(item), item, detail(hidden_reviews=3))

    assert "3 earlier reviews" in text


def test_a_capped_review_count_reads_as_a_lower_bound():
    item = pull(42)
    text = plain(inbox_with(item), item, detail(hidden_reviews=20, hidden_is_lower_bound=True))

    assert "20+ earlier reviews" in text


def test_an_unrecognised_detail_shape_falls_back_instead_of_crashing():
    item = pull(42)
    fallback = inbox_with(item).render_detail(item, object())

    assert isinstance(fallback, Text)

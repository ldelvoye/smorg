"""Tests for the GitHub inbox: two stacked bands, one flat cursor, and the detail pane."""

import io
from datetime import timedelta

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
from smorg.integrations.github.views.inbox import GitHubInbox

from .helpers import NOW, inbox_with, pull


def rendered(inbox: GitHubInbox, width: int = 100) -> str:
    console = Console(width=width, file=io.StringIO(), force_terminal=False)
    with console.capture() as capture:
        console.print(inbox.render_view())
    return capture.get()


# --- Getting back to the menu ---


def test_the_inbox_says_how_to_get_back():
    assert "‹ esc — menu" in "\n".join(inbox_with(pull(42)).content_lines())


# --- Two bands, stacked ---


def test_the_review_inbox_band_sits_above_your_pull_requests():
    lines = inbox_with(pull(), pull(51, Category.DRAFT)).content_lines()

    assert lines.index("review inbox") < lines.index("your pull requests")


def test_an_empty_category_is_hidden():
    text = "\n".join(inbox_with(pull()).content_lines())

    assert f"{Category.NEEDS_YOUR_REVIEW} (1)" in text
    assert str(Category.READY_TO_MERGE) not in text


def test_an_empty_band_reads_all_caught_up():
    """An empty band and a broken one must never look alike."""
    lines = inbox_with(pull()).content_lines()

    after_band_title = lines[lines.index("your pull requests") + 1 :]
    remaining = [line.strip() for line in after_band_title if line.strip()]
    assert remaining == ["all caught up"]


def test_a_pull_request_is_drawn_under_the_category_the_source_gave_it():
    lines = inbox_with(pull(51, Category.DRAFT)).content_lines()

    heading = lines.index(f"{Category.DRAFT} (1)")
    assert "#51" in lines[heading + 1]


# --- Rows ---


def test_a_row_names_the_repository_and_the_number():
    """A review inbox spans repositories, so a bare number identifies nothing."""
    text = "\n".join(inbox_with(pull(7, repository="octocat/tools")).content_lines())

    assert "octocat/tools#7" in text


def test_a_row_shows_the_author_and_the_age(monkeypatch):
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW + timedelta(hours=3))

    text = "\n".join(inbox_with(pull(42)).content_lines())

    assert "octocat · 3h" in text


def test_a_deleted_author_leaves_the_age_alone(monkeypatch):
    """A deleted account has author ""; the row must not render a dangling separator."""
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW + timedelta(hours=3))

    text = "\n".join(inbox_with(pull(42, author="")).content_lines())

    assert "· 3h" not in text
    assert "3h" in text


def test_a_changed_pull_request_is_marked_and_a_seen_one_is_not():
    seen = SeenState({})
    unchanged = pull(7, repository="octocat/tools")
    seen.mark_seen("github", unchanged)

    text = "\n".join(inbox_with(pull(42), unchanged, seen=seen).content_lines())
    marked = [line for line in text.splitlines() if "●" in line]

    assert any("#42" in line for line in marked)
    assert not any("#7" in line for line in marked)


# --- One cursor over every band ---


def test_the_selection_starts_at_the_first_row():
    inbox = inbox_with(pull(42), pull(51, Category.DRAFT))

    selected = inbox.selected_item()

    assert selected is not None
    assert selected.number == 42


def test_the_cursor_walks_every_band_in_order_and_wraps():
    inbox = inbox_with(
        pull(42, Category.NEEDS_YOUR_REVIEW),
        pull(43, Category.NEEDS_TEAM_REVIEW),
        pull(51, Category.DRAFT),
    )

    walked: list[int] = []
    for _ in range(4):
        selected = inbox.selected_item()
        assert selected is not None
        walked.append(selected.number)
        inbox.action_cursor_down()

    assert walked == [42, 43, 51, 42]


def test_the_cursor_clamps_when_a_refresh_shrinks_the_list():
    inbox = inbox_with(
        pull(42, Category.NEEDS_YOUR_REVIEW),
        pull(43, Category.NEEDS_TEAM_REVIEW),
        pull(51, Category.DRAFT),
    )
    inbox.action_cursor_down()
    inbox.action_cursor_down()

    inbox.panel.items = (pull(42),)
    selected = inbox.selected_item()

    assert selected is not None
    assert selected.number == 42


def test_an_empty_inbox_has_nothing_selected_and_moving_is_a_no_op():
    inbox = inbox_with()

    inbox.action_cursor_down()

    assert inbox.selected_item() is None
    assert inbox.selected_url() is None


def test_selected_url_is_the_selected_pull_requests_url():
    inbox = inbox_with(pull(42), pull(51, Category.DRAFT))

    inbox.action_cursor_down()

    assert inbox.selected_url() == "https://github.com/octocat/hello/pull/51"


# --- Server text cannot restyle the inbox ---


def test_a_title_that_looks_like_markup_is_drawn_literally():
    """Rich markup in a title would otherwise let somebody else's pull request
    colour or hide rows in your dashboard."""
    inbox = inbox_with(pull(42, title="[red]danger[/red]"))

    assert "[red]danger[/red]" in "\n".join(inbox.content_lines())


@pytest.mark.parametrize("width", [40, 60, 120])
def test_no_row_wraps_at_any_width(width):
    """A wrapped title spills into the next row's place; long titles ellipsize instead."""
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

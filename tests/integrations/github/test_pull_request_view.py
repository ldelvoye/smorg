"""Tests for the pull request view: rendering only, no network and no app."""

import io
from datetime import timedelta

from rich.console import Console

from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.github.source import (
    CheckSummary,
    Comment,
    LineCounts,
    Newest,
    PullRequestDetail,
    Reviewer,
    ReviewerState,
)
from smorg.integrations.github.views.pull_request import (
    GitHubPullRequestView,
    _format_checks_card,
)
from smorg.shell.terminal_palette import StatusColors

from .helpers import NOW, panel_with, pull

GREEN = CheckSummary(passed=14, failed=0, running=0, failed_names=())


def checks(**overrides) -> CheckSummary:
    fields = {"passed": 11, "failed": 2, "running": 1, "failed_names": ("acceptance", "typing")}
    return CheckSummary(**(fields | overrides))


def detail(**overrides) -> PullRequestDetail:
    fields = {
        "body": "Splits the loader in two.",
        "base": "main",
        "head": "tidy-loader",
        "reviewers": (
            Reviewer(name="hubot", state=ReviewerState.CHANGES_REQUESTED, submitted_at=NOW),
        ),
        "comments": Newest(items=()),
        "counts": LineCounts(additions=128, deletions=41, changed_files=6),
        "checks": GREEN,
    }
    return PullRequestDetail(**(fields | overrides))


def view_showing(shown: PullRequestDetail | None = None, error: str | None = None):
    panel = panel_with(pull(42))
    panel.viewed = pull(42)
    key = GitHubPanel.detail_key(panel.viewed)
    if shown is not None:
        panel.show_detail(key, shown)
    if error is not None:
        panel.show_detail_error(key, error)
    return GitHubPullRequestView(panel)


def rendered(view: GitHubPullRequestView) -> str:
    return "\n".join(view.content_lines())


def test_the_view_says_how_to_get_back():
    assert "‹ esc — inbox" in rendered(view_showing(detail()))


def test_the_header_names_the_pull_request():
    text = rendered(view_showing(detail()))

    assert "title of #42" in text
    assert "octocat/hello#42" in text
    assert "octocat" in text
    assert "needs your review" in text


def test_the_header_carries_branches_and_line_counts():
    text = rendered(view_showing(detail()))

    assert "tidy-loader → main" in text
    assert "+128" in text
    assert "−41" in text
    assert "6 files" in text


def test_absent_counts_hide_their_segments():
    text = rendered(view_showing(detail(counts=LineCounts())))

    assert "+-1" not in text
    assert "files" not in text


def test_all_green_checks_get_a_card_with_a_passing_line():
    text = rendered(view_showing(detail(checks=GREEN)))

    assert "checks · 14 passed" in text
    assert "✓ all 14 checks passed" in text


def test_a_truncated_green_run_does_not_claim_all():
    text = rendered(view_showing(detail(checks=CheckSummary(50, 0, 0, (), truncated=True))))

    assert "50+ checks passed" in text
    assert "all" not in text.split("checks passed")[0].splitlines()[-1]
    assert "checks · 50 passed · …" in text


def test_failed_checks_get_a_card_naming_them():
    text = rendered(view_showing(detail(checks=checks())))

    assert "checks · 2 failed · 11 passed · 1 running" in text
    assert "✗ acceptance" in text
    assert "✗ typing" in text


def test_failed_names_beyond_the_cap_are_counted():
    text = rendered(view_showing(detail(checks=checks(failed=12, hidden_failed=10))))

    assert "… 10 more failed" in text


def test_unavailable_checks_read_as_no_checks():
    text = rendered(view_showing(detail(checks=CheckSummary(0, 0, 0, (), available=False))))

    assert "no checks" in text


def test_zero_checks_show_nothing_at_all():
    text = rendered(view_showing(detail(checks=CheckSummary(0, 0, 0, ()))))

    assert "checks" not in text


def test_a_missing_description_says_so():
    assert "no description" in rendered(view_showing(detail(body="")))


def test_reviewer_lines_carry_their_signs(monkeypatch):
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW + timedelta(hours=3))
    lines = (
        Reviewer(name="alice", state=ReviewerState.REQUESTED, submitted_at=None),
        Reviewer(name="hubot", state=ReviewerState.CHANGES_REQUESTED, submitted_at=NOW),
        Reviewer(name="monalisa", state=ReviewerState.APPROVED, submitted_at=NOW),
        Reviewer(name="wedamija", state=ReviewerState.LEFT_COMMENTS, submitted_at=NOW),
    )

    text = rendered(view_showing(detail(reviewers=lines)))

    assert "● alice · requested" in text
    assert "✗ hubot · changes requested · 3h" in text
    assert "✓ monalisa · approved · 3h" in text
    assert "✎ wedamija · left comments · 3h" in text
    assert "reviews (4)" in text


def test_no_reviewers_no_reviews_card():
    assert "reviews" not in rendered(view_showing(detail(reviewers=())))


def test_reviewer_lines_beyond_the_cap_are_counted():
    many = tuple(
        Reviewer(name=f"user{index}", state=ReviewerState.APPROVED, submitted_at=NOW)
        for index in range(13)
    )

    text = rendered(view_showing(detail(reviewers=many)))

    assert "… 3 more reviewers" in text


def test_an_all_green_checks_title_is_still_counted():
    text = rendered(view_showing(detail(checks=GREEN)))

    assert "checks · 14 passed" in text


def test_comments_show_author_age_and_body(monkeypatch):
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW + timedelta(hours=2))
    alice = Comment(author="alice", submitted_at=NOW, body="The retry cap seems low.")

    text = rendered(view_showing(detail(comments=Newest(items=(alice,)))))

    assert "comments (1)" in text
    assert "alice · 2h" in text
    assert "The retry cap seems low." in text


def test_older_comments_are_counted():
    alice = Comment(author="alice", submitted_at=NOW, body="hi")

    text = rendered(view_showing(detail(comments=Newest(items=(alice,), hidden=9))))

    assert "… 9 earlier comments" in text


def test_a_deleted_comment_author_reads_as_someone():
    ghost = Comment(author="", submitted_at=None, body="hi")

    text = rendered(view_showing(detail(comments=Newest(items=(ghost,)))))

    assert "someone" in text


def test_empty_sections_have_no_cards():
    text = rendered(view_showing(detail(reviewers=())))

    assert "reviews" not in text
    assert "comments" not in text


def test_open_targets_the_viewed_pull_request(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "smorg.integrations.github.views.pull_request.webbrowser.open",
        lambda url: opened.append(url),
    )
    view = view_showing(detail())

    view.action_open_in_github()

    assert opened == ["https://github.com/octocat/hello/pull/42"]


def test_no_detail_yet_reads_as_loading():
    assert "loading…" in rendered(view_showing())


def test_a_failed_load_reads_as_an_error():
    text = rendered(view_showing(error="boom"))

    assert "could not load: boom" in text
    assert "loading…" not in text


def test_the_cards_read_checks_reviews_description_comments():
    text = rendered(view_showing(detail(checks=checks())))

    checks_at = text.index("checks ·")
    reviews_at = text.index("reviews (")
    description_at = text.index("description")
    assert checks_at < reviews_at < description_at


def test_card_titles_escape_the_borders_dim():
    """The dim border must not wash a title's color: bold + truecolor, never dim."""
    shades = StatusColors(red="#cf222e", yellow="#9a6700", green="#1a7f37")
    card = _format_checks_card(checks(), shades)

    console = Console(width=60, file=io.StringIO(), force_terminal=True, color_system="truecolor")
    with console.capture() as capture:
        console.print(card)

    top_line = capture.get().splitlines()[0]
    assert "\x1b[1;38;2;207;34;46m" in top_line

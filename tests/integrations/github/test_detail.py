"""Tests for the GitHub source's pull request detail: body, branches, reviewers, checks,
counts, and comments.
"""

import json
from datetime import UTC, datetime

import httpx
import pytest

from smorg.core.contract import AuthExpired
from smorg.integrations.github.source import (
    ABSENT_COUNT,
    Category,
    PullRequest,
    Reviewer,
    ReviewerState,
    fetch_detail,
)
from smorg.integrations.github.source.detail import CHECK_RUNS_FETCH_LIMIT, COMMENTS_FETCH_LIMIT

from .recorded import CREDENTIALS, FIXTURES

PULL = json.loads((FIXTURES / "github_pull.json").read_text())
REVIEWS = json.loads((FIXTURES / "github_reviews.json").read_text())


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError("PyGithub brings its own transport; fetch_detail's client must go unused")


# Handed to fetch_detail calls, and wired to fail if anything ever reaches it: PyGithub owns
# that path's transport, so the shell's shared client has nothing to do there.
UNUSED_HTTP = httpx.Client(transport=httpx.MockTransport(_refuse))


ITEM = PullRequest(
    id="octocat/hello#42",
    updated_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
    url="https://github.com/octocat/hello/pull/42",
    number=42,
    title="Tidy the loader",
    repository="octocat/hello",
    author="octocat",
    category=Category.NEEDS_YOUR_REVIEW,
)

HEAD_SHA = "2222222222222222222222222222222222222222"

CHECK_RUNS = {
    "total_count": 3,
    "check_runs": [
        {"name": "acceptance", "status": "completed", "conclusion": "failure"},
        {"name": "backend typing", "status": "completed", "conclusion": "success"},
        {"name": "deploy", "status": "in_progress", "conclusion": None},
    ],
}

STATUSES = {
    "state": "failure",
    "statuses": [{"context": "ci/legacy", "state": "failure"}],
}

COMMENTS = [
    {
        "user": {"login": "alice"},
        "body": "Looks good but the retry cap seems low.",
        "created_at": "2026-08-13T10:00:00Z",
    },
    {"user": {"login": "bob"}, "body": "Agreed.", "created_at": "2026-08-13T11:00:00Z"},
]

NO_RUNS = {"total_count": 0, "check_runs": []}
NO_STATUSES = {"state": "pending", "statuses": []}


def serving_detail(
    github,
    pull: dict | None = None,
    reviews: list | None = None,
    check_runs: dict | None = None,
    status: dict | None = None,
    comments: list | None = None,
) -> None:
    """Register every endpoint one fetch_detail call reads, defaulting to the quiet case."""
    if pull is None:
        pull = PULL
    if reviews is None:
        reviews = []
    if check_runs is None:
        check_runs = NO_RUNS
    if status is None:
        status = NO_STATUSES
    if comments is None:
        comments = []
    github.serving("/repos/octocat/hello/pulls/42", pull)
    github.serving("/repos/octocat/hello/pulls/42/reviews", reviews)
    github.serving(f"/repos/octocat/hello/commits/{HEAD_SHA}/check-runs", check_runs)
    github.serving(f"/repos/octocat/hello/commits/{HEAD_SHA}/status", status)
    github.serving("/repos/octocat/hello/issues/42/comments", comments)


# --- The pull request detail ---


def test_detail_carries_the_body_the_branches_and_the_reviews(github):
    serving_detail(github, reviews=REVIEWS)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert "Splits the loader in two." in detail.body
    assert detail.base == "main"
    assert detail.head == "tidy-loader"
    hubot = Reviewer(
        name="hubot",
        state=ReviewerState.CHANGES_REQUESTED,
        submitted_at=datetime(2026, 8, 12, 10, 0, tzinfo=UTC),
    )
    monalisa = Reviewer(
        name="monalisa",
        state=ReviewerState.APPROVED,
        submitted_at=datetime(2026, 8, 13, 11, 0, tzinfo=UTC),
    )
    assert detail.reviewers == (hubot, monalisa)


def test_detail_costs_one_request_per_thing_it_shows(github):
    """The repository is addressed by name and never read, so it is not
    fetched — every request behind the pull request view is one of the
    five things it shows."""
    serving_detail(github, reviews=REVIEWS)

    fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert sorted(github.paths) == sorted(
        [
            "/repos/octocat/hello/pulls/42",
            "/repos/octocat/hello/pulls/42/reviews",
            f"/repos/octocat/hello/commits/{HEAD_SHA}/check-runs",
            f"/repos/octocat/hello/commits/{HEAD_SHA}/status",
            "/repos/octocat/hello/issues/42/comments",
        ]
    )


def test_a_body_carrying_terminal_escapes_is_sanitised_without_losing_its_lines(github):
    """Dropping the escape byte is what makes the sequence inert; the "[31m"
    left behind is literal text a terminal draws rather than obeys. Newlines
    survive, since a description is rendered as markdown."""
    serving_detail(github, pull=PULL | {"body": "one\x1b[31m\ntwo\x00"})

    body = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).body

    assert "\x1b" not in body
    assert "\x00" not in body
    assert len(body.splitlines()) == 2


def test_a_pull_request_with_no_body_reads_as_empty_not_missing(github):
    serving_detail(github, pull=PULL | {"body": None})

    assert fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).body == ""


def test_a_detail_failure_is_an_integration_error(github):
    serving_detail(github)
    github.serving("/repos/octocat/hello/pulls/42", {"message": "Bad credentials"}, status=401)

    with pytest.raises(AuthExpired):
        fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)


def test_detail_carries_the_line_counts(github):
    serving_detail(github)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert detail.counts.additions == 128
    assert detail.counts.deletions == 41
    assert detail.counts.changed_files == 6
    assert detail.counts.commits == 2


def test_missing_line_counts_read_as_absent_not_zero(github):
    hostile = PULL | {"additions": None, "deletions": "nan", "changed_files": None}
    serving_detail(github, pull=hostile)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert detail.counts.additions == ABSENT_COUNT
    assert detail.counts.deletions == ABSENT_COUNT
    assert detail.counts.changed_files == ABSENT_COUNT


def test_checks_merge_runs_with_legacy_statuses(github):
    serving_detail(github, check_runs=CHECK_RUNS, status=STATUSES)

    checks = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).checks

    assert checks.available is True
    assert checks.passed == 1
    assert checks.failed == 2
    assert checks.running == 1
    assert checks.failed_names == ("acceptance", "ci/legacy")


@pytest.mark.parametrize(
    "conclusion,expect",
    [
        ("success", "passed"),
        ("neutral", "passed"),
        ("skipped", "passed"),
        ("failure", "failed"),
        ("timed_out", "failed"),
        ("cancelled", "failed"),
        ("action_required", "failed"),
        (None, "running"),
        ("mystery", "running"),
    ],
)
def test_every_run_conclusion_lands_in_a_bucket(github, conclusion, expect):
    runs = {
        "total_count": 1,
        "check_runs": [{"name": "one", "status": "completed", "conclusion": conclusion}],
    }
    serving_detail(github, check_runs=runs)

    checks = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).checks

    counts = {"passed": checks.passed, "failed": checks.failed, "running": checks.running}
    assert counts[expect] == 1
    assert sum(counts.values()) == 1


@pytest.mark.parametrize(
    "state,expect",
    [("success", "passed"), ("failure", "failed"), ("error", "failed"), ("pending", "running")],
)
def test_every_legacy_status_state_lands_in_a_bucket(github, state, expect):
    status = {"state": state, "statuses": [{"context": "ci/legacy", "state": state}]}
    serving_detail(github, status=status)

    checks = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).checks

    counts = {"passed": checks.passed, "failed": checks.failed, "running": checks.running}
    assert counts[expect] == 1
    assert sum(counts.values()) == 1


def test_failed_names_are_capped_with_a_count_of_the_rest(github):
    failing = [
        {"name": f"job {index}", "status": "completed", "conclusion": "failure"}
        for index in range(12)
    ]
    serving_detail(github, check_runs={"total_count": 12, "check_runs": failing})

    checks = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).checks

    assert checks.failed == 12
    assert len(checks.failed_names) == 10
    assert checks.hidden_failed == 2


def test_a_run_list_at_the_cap_reads_as_truncated(github):
    passing = [
        {"name": f"job {index}", "status": "completed", "conclusion": "success"}
        for index in range(CHECK_RUNS_FETCH_LIMIT)
    ]
    serving_detail(github, check_runs={"total_count": 250, "check_runs": passing})

    checks = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).checks

    assert checks.truncated is True
    assert checks.passed == CHECK_RUNS_FETCH_LIMIT


def test_an_unreadable_checks_endpoint_degrades_to_no_summary(github):
    serving_detail(github)
    github.serving(
        f"/repos/octocat/hello/commits/{HEAD_SHA}/check-runs", {"message": "no"}, status=500
    )

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert detail.checks.available is False
    assert "Splits the loader in two." in detail.body


def test_a_run_name_carrying_escapes_is_sanitised(github):
    runs = {
        "total_count": 1,
        "check_runs": [{"name": "acc\x1b[31mept", "status": "completed", "conclusion": "failure"}],
    }
    serving_detail(github, check_runs=runs)

    checks = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).checks

    assert "\x1b" not in checks.failed_names[0]


def test_detail_carries_the_newest_comments_oldest_first(github):
    serving_detail(github, comments=COMMENTS)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert [comment.author for comment in detail.comments.items] == ["alice", "bob"]
    assert detail.comments.items[0].body == "Looks good but the retry cap seems low."
    assert detail.comments.hidden == 0


def test_old_comments_are_counted_rather_than_shown(github):
    many = [
        {
            "user": {"login": f"user{index}"},
            "body": f"c{index}",
            "created_at": "2026-08-13T10:00:00Z",
        }
        for index in range(9)
    ]
    serving_detail(github, comments=many)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert [comment.body for comment in detail.comments.items] == ["c4", "c5", "c6", "c7", "c8"]
    assert detail.comments.hidden == 4
    assert detail.comments.hidden_is_lower_bound is False


def test_a_comment_list_at_the_cap_reads_as_a_lower_bound(github):
    many = [
        {"user": {"login": "who"}, "body": f"c{index}", "created_at": "2026-08-13T10:00:00Z"}
        for index in range(COMMENTS_FETCH_LIMIT)
    ]
    serving_detail(github, comments=many)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert detail.comments.hidden_is_lower_bound is True


def test_a_comment_survives_a_deleted_account_and_a_hostile_body(github):
    hostile = [{"user": None, "body": "hi\x1b[31m", "created_at": "2026-08-13T10:00:00Z"}]
    serving_detail(github, comments=hostile)

    comment = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).comments.items[0]

    assert comment.author == ""
    assert "\x1b" not in comment.body


def test_requested_users_and_teams_lead_the_reviewer_lines(github):
    asked = PULL | {
        "requested_reviewers": [{"login": "alice"}],
        "requested_teams": [{"slug": "sre-production-engineering"}],
    }
    serving_detail(github, pull=asked, reviews=REVIEWS)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    names = [reviewer.name for reviewer in detail.reviewers]
    assert names[:2] == ["alice", "#sre-production-engineering"]
    assert detail.reviewers[0].state is ReviewerState.REQUESTED
    assert detail.reviewers[0].submitted_at is None


def test_nobody_requested_reads_as_empty(github):
    serving_detail(github)

    assert fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).reviewers == ()


def test_a_reviewer_name_carrying_escapes_is_sanitised(github):
    asked = PULL | {"requested_reviewers": [{"login": "al\x1b[31mice"}]}
    serving_detail(github, pull=asked)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert "\x1b" not in detail.reviewers[0].name


def _review_event(login: str, state: str, submitted_at: str) -> dict:
    return {"user": {"login": login}, "state": state, "body": "", "submitted_at": submitted_at}


def test_the_authors_comment_wrappers_are_not_reviewer_states(github):
    events = [
        _review_event("octocat", "COMMENTED", "2026-08-12T10:00:00Z"),
        _review_event("octocat", "COMMENTED", "2026-08-12T10:05:00Z"),
    ]
    serving_detail(github, reviews=events)

    assert fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).reviewers == ()


def test_a_later_comment_never_downgrades_an_approval(github):
    events = [
        _review_event("wedamija", "APPROVED", "2026-08-12T10:00:00Z"),
        _review_event("wedamija", "COMMENTED", "2026-08-12T11:00:00Z"),
    ]
    serving_detail(github, reviews=events)

    reviewer = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).reviewers[0]

    assert reviewer.state is ReviewerState.APPROVED


def test_a_reviewer_with_only_comments_left_comments(github):
    events = [_review_event("wedamija", "COMMENTED", "2026-08-12T10:00:00Z")]
    serving_detail(github, reviews=events)

    reviewer = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).reviewers[0]

    assert reviewer.state is ReviewerState.LEFT_COMMENTS


def test_a_re_requested_reviewer_reads_as_requested_again(github):
    asked = PULL | {"requested_reviewers": [{"login": "wedamija"}]}
    events = [_review_event("wedamija", "APPROVED", "2026-08-12T10:00:00Z")]
    serving_detail(github, pull=asked, reviews=events)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    states = [reviewer.state for reviewer in detail.reviewers]
    assert states == [ReviewerState.REQUESTED]


def test_a_dismissed_review_reads_as_dismissed(github):
    events = [_review_event("wedamija", "DISMISSED", "2026-08-12T10:00:00Z")]
    serving_detail(github, reviews=events)

    reviewer = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).reviewers[0]

    assert reviewer.state is ReviewerState.DISMISSED

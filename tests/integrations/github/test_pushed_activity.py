"""Tests for the per-repo activity lookup: which rows count as the viewer's recent pushes."""

from datetime import UTC, datetime, timedelta

import httpx

from smorg.integrations.github.source.pushed.activity import (
    HOT_TIME_PERIOD,
    RepoActivity,
    activity_lookup,
)
from smorg.integrations.github.source.pushed.qualification import WINDOW

from .recorded import CREDENTIALS, graphql_http

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
_FRESH = (NOW - timedelta(days=1)).isoformat()
_STALE = (NOW - WINDOW - timedelta(days=1)).isoformat()


def _row(
    ref: str = "refs/heads/feature-branch",
    timestamp: str = _FRESH,
    activity_type: str = "push",
) -> dict:
    return {"ref": ref, "timestamp": timestamp, "activity_type": activity_type}


def _lookup(rows: object) -> RepoActivity | None:
    http = graphql_http(activity={"octocat/hello": rows})
    return activity_lookup(CREDENTIALS, http, "octocat/hello", "octocat", NOW, HOT_TIME_PERIOD)


def test_push_force_push_and_branch_creation_rows_become_pairs():
    rows = [
        _row(activity_type="push"),
        _row(ref="refs/heads/rebased", activity_type="force_push"),
        _row(ref="refs/heads/brand-new", activity_type="branch_creation"),
    ]

    result = _lookup(rows)

    assert result is not None
    assert [pair.branch for pair in result.pairs] == ["feature-branch", "rebased", "brand-new"]
    assert all(pair.repository == "octocat/hello" for pair in result.pairs)


def test_rows_failing_a_keep_filter_are_dropped():
    rows = [
        _row(activity_type="branch_deletion"),
        _row(activity_type="pr_merge"),
        _row(timestamp=_STALE),
        _row(ref="not-a-heads-ref"),
        {"activity_type": "push"},
    ]

    result = _lookup(rows)

    assert result is not None
    assert result.pairs == []


def test_a_failure_returns_none_rather_than_raising():
    assert _lookup(b"not json") is None
    assert _lookup(500) is None
    assert _lookup({"not": "a list"}) is None


def test_the_activity_request_pins_the_viewer_as_actor():
    seen_params: dict[str, str] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    http = httpx.Client(transport=httpx.MockTransport(respond))
    result = activity_lookup(CREDENTIALS, http, "octocat/hello", "octocat", NOW, HOT_TIME_PERIOD)

    assert result is not None
    assert result.pairs == []
    assert seen_params["actor"] == "octocat"


def test_an_out_of_window_push_still_reports_its_timestamp():
    """A 31-90 day old push must land the repo in the cold band, not "proven never active"."""
    stamp = NOW - WINDOW - timedelta(days=15)
    rows = [_row(timestamp=stamp.isoformat())]

    result = _lookup(rows)

    assert result is not None
    assert result.pairs == []
    assert result.newest == stamp

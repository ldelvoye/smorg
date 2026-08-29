"""Tests for the per-repo activity lookup: which rows count as the viewer's recent pushes."""

from datetime import UTC, datetime, timedelta

import httpx

from smorg.integrations.github.source.pushed.activity import HOT_TIME_PERIOD, activity_pairs
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


def _pairs(rows: object) -> list | None:
    http = graphql_http(activity={"octocat/hello": rows})
    return activity_pairs(CREDENTIALS, http, "octocat/hello", "octocat", NOW, HOT_TIME_PERIOD)


def test_push_force_push_and_branch_creation_rows_become_pairs():
    rows = [
        _row(activity_type="push"),
        _row(ref="refs/heads/rebased", activity_type="force_push"),
        _row(ref="refs/heads/brand-new", activity_type="branch_creation"),
    ]

    pairs = _pairs(rows)

    assert pairs is not None
    assert [pair.branch for pair in pairs] == ["feature-branch", "rebased", "brand-new"]
    assert all(pair.repository == "octocat/hello" for pair in pairs)


def test_rows_failing_a_keep_filter_are_dropped():
    rows = [
        _row(activity_type="branch_deletion"),
        _row(activity_type="pr_merge"),
        _row(timestamp=_STALE),
        _row(ref="not-a-heads-ref"),
        {"activity_type": "push"},
    ]

    pairs = _pairs(rows)

    assert pairs == []


def test_a_failure_returns_none_rather_than_raising():
    assert _pairs(b"not json") is None
    assert _pairs(500) is None
    assert _pairs({"not": "a list"}) is None


def test_the_activity_request_pins_the_viewer_as_actor():
    seen_params: dict[str, str] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    http = httpx.Client(transport=httpx.MockTransport(respond))
    pairs = activity_pairs(CREDENTIALS, http, "octocat/hello", "octocat", NOW, HOT_TIME_PERIOD)

    assert pairs == []
    assert seen_params["actor"] == "octocat"

"""Tests for the feed tripwire: repo names it lifts out of the viewer's event feed."""

from datetime import UTC, datetime

from smorg.integrations.github.source.pushed.feed import pushed_repo_stamps

from .recorded import CREDENTIALS, graphql_http


def _event(
    repo: str, created_at: str, event_type: str = "PushEvent", ref_type: str | None = None
) -> dict:
    event = {"type": event_type, "created_at": created_at, "repo": {"name": repo}}
    if ref_type is not None:
        event["payload"] = {"ref_type": ref_type}
    return event


def test_push_and_create_events_stamp_their_repos_newest_first():
    events = [
        _event("octocat/hello", "2026-08-28T10:00:00Z"),
        _event(
            "octocat/hello", "2026-08-28T11:00:00Z", event_type="CreateEvent", ref_type="branch"
        ),
        _event("acme/widgets", "2026-08-28T09:00:00Z"),
        _event("acme/ignored", "2026-08-28T09:00:00Z", event_type="WatchEvent"),
        _event("acme/tags", "2026-08-28T09:30:00Z", event_type="CreateEvent", ref_type="tag"),
        {"type": "PushEvent"},
    ]

    stamps = pushed_repo_stamps(CREDENTIALS, graphql_http(events=events), "octocat")

    assert stamps == {
        "octocat/hello": datetime(2026, 8, 28, 11, 0, tzinfo=UTC),
        "acme/widgets": datetime(2026, 8, 28, 9, 0, tzinfo=UTC),
    }


def test_a_feed_failure_yields_no_stamps():
    assert pushed_repo_stamps(CREDENTIALS, graphql_http(events=b"not json"), "octocat") == {}
    assert pushed_repo_stamps(CREDENTIALS, graphql_http(events_status=500), "octocat") == {}

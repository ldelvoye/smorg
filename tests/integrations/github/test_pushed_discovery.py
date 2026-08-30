"""Tests for pushed-branches repo discovery: the owned + contributed union and its window."""

from datetime import UTC, datetime, timedelta

from smorg.integrations.github.source.pushed.discovery import discover_repos
from smorg.integrations.github.source.pushed.qualification import WINDOW

from .recorded import CREDENTIALS, graphql_http

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
_FRESH = (NOW - timedelta(days=1)).isoformat()
_STALE = (NOW - WINDOW - timedelta(days=1)).isoformat()


def _discovery_payload(owned: list[dict], contributed: list[dict]) -> dict:
    return {
        "data": {
            "viewer": {
                "login": "octocat",
                "repositories": {"nodes": owned},
                "repositoriesContributedTo": {"nodes": contributed},
            }
        }
    }


def _repo(name: str = "octocat/hello", pushed_at: str = _FRESH) -> dict:
    return {"nameWithOwner": name, "pushedAt": pushed_at}


def test_owned_and_contributed_repos_union_without_duplicates():
    payload = _discovery_payload(
        owned=[_repo("octocat/hello"), _repo("octocat/shared")],
        contributed=[_repo("octocat/shared"), _repo("acme/widgets")],
    )

    result = discover_repos(CREDENTIALS, graphql_http(discovery=payload), NOW)

    assert result is not None
    login, candidates = result
    assert login == "octocat"
    assert [candidate.name for candidate in candidates] == [
        "octocat/hello",
        "octocat/shared",
        "acme/widgets",
    ]


def test_a_repo_last_pushed_outside_the_window_is_not_a_candidate():
    payload = _discovery_payload(owned=[_repo(pushed_at=_STALE)], contributed=[])

    result = discover_repos(CREDENTIALS, graphql_http(discovery=payload), NOW)

    assert result is not None
    _, candidates = result
    assert candidates == []


def test_a_malformed_repo_node_is_skipped_without_losing_the_rest():
    payload = _discovery_payload(
        owned=[{"nameWithOwner": None, "pushedAt": _FRESH}, _repo("octocat/hello")],
        contributed=[],
    )

    result = discover_repos(CREDENTIALS, graphql_http(discovery=payload), NOW)

    assert result is not None
    _, candidates = result
    assert [candidate.name for candidate in candidates] == ["octocat/hello"]


def test_a_transport_or_shape_failure_returns_none():
    assert discover_repos(CREDENTIALS, graphql_http(discovery=b"not json"), NOW) is None
    assert discover_repos(CREDENTIALS, graphql_http(discovery_status=500), NOW) is None
    assert discover_repos(CREDENTIALS, graphql_http(discovery={"data": {}}), NOW) is None

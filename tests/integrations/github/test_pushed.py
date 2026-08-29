"""Tests for the GitHub source's pushed-branches list: pair collapse, qualification over
GraphQL, and the pipeline's degradation into unavailable or partial results.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from smorg.integrations.github.source.pushed import (
    MAX_BRANCHES,
    MAX_PAIRS,
    PushPair,
    _newest_pairs,
    _qualification_query,
    _qualified_branches_of,
    query_pushed_branches,
)

from .recorded import CREDENTIALS, graphql_http

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def _pair(
    repository: str = "octocat/hello",
    branch: str = "feature-branch",
    pushed_at: datetime = NOW,
) -> PushPair:
    return PushPair(repository=repository, branch=branch, pushed_at=pushed_at)


def _qualified_repository(
    default_branch: str | None = "main",
    headline: str = "Fix the loader race",
    parent_count: int = 1,
    associated_pull_requests: int = 0,
    ref_present: bool = True,
) -> dict:
    """One aliased repository/ref lookup, shaped like the live qualification query's
    response, with qualifying defaults.
    """
    if default_branch is None:
        default_branch_field = None
    else:
        default_branch_field = {"name": default_branch}
    if not ref_present:
        ref_field = None
    else:
        ref_field = {
            "associatedPullRequests": {"totalCount": associated_pull_requests},
            "target": {"messageHeadline": headline, "parents": {"totalCount": parent_count}},
        }
    return {"defaultBranchRef": default_branch_field, "ref": ref_field}


def _qualification_payload(*repositories: dict) -> dict:
    """The qualification GraphQL response shape: one aliased field per repository, in order."""
    data: dict[str, dict] = {}
    for index, repository in enumerate(repositories):
        data[f"b{index}"] = repository
    return {"data": data}


def test_duplicate_pairs_collapse_to_the_newest_push_and_cap_at_max_pairs():
    older = PushPair("octocat/hello", "feature-branch", NOW - timedelta(days=2))
    newer = PushPair("octocat/hello", "feature-branch", NOW - timedelta(days=1))
    others = [
        PushPair("octocat/hello", f"branch-{index}", NOW - timedelta(days=3))
        for index in range(MAX_PAIRS + 5)
    ]

    pairs = _newest_pairs([older, newer, *others])

    assert len(pairs) == MAX_PAIRS
    assert pairs[0].pushed_at == newer.pushed_at


# --- Qualification: which pairs become branches ---


_DROPPED_QUALIFICATION_CASES: tuple[tuple[str, dict], ...] = (
    ("branch deleted since the push", {"ref_present": False}),
    ("the pushed branch is the default branch", {"default_branch": "feature-branch"}),
    ("already has a pull request", {"associated_pull_requests": 1}),
    ("a merge tip", {"parent_count": 2}),
)


@pytest.mark.parametrize(("label", "overrides"), _DROPPED_QUALIFICATION_CASES)
def test_a_pair_failing_a_keep_filter_is_dropped(label, overrides):
    pair = _pair(branch="feature-branch")
    repository = _qualified_repository(**overrides)

    result = _qualified_branches_of(_qualification_payload(repository), [pair])

    assert result.branches == (), label


def test_a_pair_pointing_at_a_non_commit_target_is_dropped():
    """A ref pointing at a tag object carries none of the Commit fields the query asked for."""
    pair = _pair()
    repository = {
        "defaultBranchRef": {"name": "main"},
        "ref": {"associatedPullRequests": {"totalCount": 0}, "target": {}},
    }

    result = _qualified_branches_of(_qualification_payload(repository), [pair])

    assert result.branches == ()


def test_a_qualifying_pair_becomes_a_pushed_branch_with_the_push_time():
    pair = _pair(
        repository="octocat/hello",
        branch="fix/loader-race",
        pushed_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
    )
    repository = _qualified_repository(headline="Fix the loader race")

    result = _qualified_branches_of(_qualification_payload(repository), [pair])

    assert len(result.branches) == 1
    branch = result.branches[0]
    assert branch.id == "octocat/hello:fix/loader-race"
    assert branch.url == "https://github.com/octocat/hello/tree/fix/loader-race"
    assert branch.compare_url == "https://github.com/octocat/hello/pull/new/fix/loader-race"
    assert branch.headline == "Fix the loader race"
    assert branch.updated_at == datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def test_qualified_branches_are_capped_at_max_branches():
    count = MAX_BRANCHES + 5
    pairs = [_pair(branch=f"branch-{index}") for index in range(count)]
    repositories = [_qualified_repository() for _ in range(count)]

    result = _qualified_branches_of(_qualification_payload(*repositories), pairs)

    assert len(result.branches) == MAX_BRANCHES


def test_qualification_asks_only_about_open_and_merged_pull_requests():
    """A branch whose PRs were all closed unmerged still needs a PR, so it must not be
    disqualified by them.
    """
    query = _qualification_query([_pair()])

    assert "associatedPullRequests(states: [OPEN, MERGED], first: 1)" in query


def _activity_row(branch: str, days_ago: int = 1) -> dict:
    timestamp = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    return {"ref": f"refs/heads/{branch}", "timestamp": timestamp, "activity_type": "push"}


def _pipeline_http(rows: list[dict], pushed: object, **overrides) -> httpx.Client:
    discovery = _single_repo_discovery()
    return graphql_http(
        discovery=discovery, activity={"octocat/hello": rows}, pushed=pushed, **overrides
    )


def _single_repo_discovery() -> dict:
    fresh = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    node = {"nameWithOwner": "octocat/hello", "pushedAt": fresh}
    return {
        "data": {
            "viewer": {
                "login": "octocat",
                "repositories": {"nodes": [node]},
                "repositoriesContributedTo": {"nodes": []},
            }
        }
    }


# --- Escaping ---


def test_a_hostile_branch_name_round_trips_through_the_transport():
    rows = [_activity_row('fix/"weird"\\branch')]
    http = _pipeline_http(rows, _qualification_payload(_qualified_repository()))

    result = query_pushed_branches(CREDENTIALS, http)

    assert result.unavailable is False
    assert [branch.branch for branch in result.branches] == ['fix/"weird"\\branch']


# --- Ordering ---


def test_two_branches_come_back_newest_push_first():
    rows = [_activity_row("old", days_ago=5), _activity_row("new", days_ago=1)]
    qualification = _qualification_payload(_qualified_repository(), _qualified_repository())
    http = _pipeline_http(rows, qualification)

    result = query_pushed_branches(CREDENTIALS, http)

    assert [branch.branch for branch in result.branches] == ["new", "old"]


# --- Degradation: transport, HTTP, and shape failures never raise ---


def _failing_http() -> httpx.Client:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    return httpx.Client(transport=httpx.MockTransport(refuse))


@pytest.mark.parametrize(
    "http_factory",
    [
        _failing_http,
        lambda: graphql_http(discovery=b"not json"),
        lambda: graphql_http(discovery_status=500),
        lambda: _pipeline_http([_activity_row("kept")], pushed=b"not json"),
        lambda: _pipeline_http([_activity_row("kept")], pushed={"data": {}}, pushed_status=403),
    ],
)
def test_a_shape_or_transport_surprise_degrades_to_unavailable(http_factory):
    result = query_pushed_branches(CREDENTIALS, http_factory())

    assert result.unavailable is True
    assert result.branches == ()


def test_one_failing_repo_does_not_blank_the_others():
    fresh = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    nodes = [
        {"nameWithOwner": "octocat/hello", "pushedAt": fresh},
        {"nameWithOwner": "octocat/broken", "pushedAt": fresh},
    ]
    discovery = {
        "data": {
            "viewer": {
                "login": "octocat",
                "repositories": {"nodes": nodes},
                "repositoriesContributedTo": {"nodes": []},
            }
        }
    }
    activity = {"octocat/hello": [_activity_row("kept")], "octocat/broken": 403}
    pushed = _qualification_payload(_qualified_repository())
    http = graphql_http(discovery=discovery, activity=activity, pushed=pushed)

    result = query_pushed_branches(CREDENTIALS, http)

    assert result.unavailable is False
    assert [branch.branch for branch in result.branches] == ["kept"]


def _http_forbidding_graphql() -> httpx.Client:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/repos/") and request.url.path.endswith("/activity"):
            return httpx.Response(200, json=[])
        if b"repositoriesContributedTo" in request.content:
            return httpx.Response(200, json=_single_repo_discovery())
        raise AssertionError("no qualification GraphQL request should happen without pairs")

    return httpx.Client(transport=httpx.MockTransport(respond))


def test_zero_pairs_returns_an_available_empty_container_without_a_graphql_call():
    result = query_pushed_branches(CREDENTIALS, _http_forbidding_graphql())

    assert result.unavailable is False
    assert result.branches == ()

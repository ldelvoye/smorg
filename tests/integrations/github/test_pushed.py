"""Tests for the GitHub source's pushed-branches list: discovery from the REST event feed,
qualification over GraphQL, and the translation of failures into an unavailable container.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from smorg.integrations.github.source.pushed import (
    MAX_BRANCHES,
    MAX_PAIRS,
    WINDOW,
    _pushed_pairs_of,
    _PushPair,
    _qualified_branches_of,
    query_pushed_branches,
)

from .recorded import CREDENTIALS, graphql_http

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
_STALE = (NOW - WINDOW - timedelta(days=1)).isoformat()


def _push_event(
    repo: str = "octocat/hello",
    branch: str = "feature-branch",
    created_at: str = "2026-08-18T12:00:00Z",
    event_type: str = "PushEvent",
    ref_prefix: str = "refs/heads/",
) -> dict:
    """A GitHub REST event, shaped like the viewer's public event feed."""
    return {
        "type": event_type,
        "created_at": created_at,
        "repo": {"name": repo},
        "payload": {"ref": f"{ref_prefix}{branch}"},
    }


def _recent_push_event(branch: str = "feature-branch") -> dict:
    created_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    return _push_event(branch=branch, created_at=created_at)


def _create_event(
    repo: str = "octocat/hello",
    branch: object = "feature-branch",
    created_at: str = "2026-08-18T12:00:00Z",
    ref_type: str = "branch",
) -> dict:
    """A GitHub REST creation event, shaped like the viewer's event feed; branch creations
    carry a bare ref name, tag and repository creations are the non-qualifying shapes.
    """
    return {
        "type": "CreateEvent",
        "created_at": created_at,
        "repo": {"name": repo},
        "payload": {"ref": branch, "ref_type": ref_type},
    }


def _pair(
    repository: str = "octocat/hello",
    branch: str = "feature-branch",
    pushed_at: datetime = NOW,
) -> _PushPair:
    return _PushPair(repository=repository, branch=branch, pushed_at=pushed_at)


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


# --- Discovery: which events become pairs ---


_DROPPED_EVENT_CASES: tuple[tuple[str, dict], ...] = (
    ("not a push event", {"event_type": "WatchEvent"}),
    ("a tag ref, not a branch", {"branch": "v1.0", "ref_prefix": "refs/tags/"}),
    ("a naive timestamp", {"created_at": "2026-08-18T12:00:00"}),
    ("older than the window", {"created_at": _STALE}),
)


@pytest.mark.parametrize(("label", "overrides"), _DROPPED_EVENT_CASES)
def test_an_event_failing_a_keep_filter_is_dropped(label, overrides):
    event = _push_event(**overrides)

    pairs = _pushed_pairs_of([[event]], NOW)

    assert pairs == [], label


def test_a_branch_creation_counts_as_a_push():
    """GitHub files a new branch's first push as a CreateEvent, never a PushEvent."""
    pairs = _pushed_pairs_of([[_create_event()]], NOW)

    assert len(pairs) == 1
    assert pairs[0].branch == "feature-branch"
    assert pairs[0].repository == "octocat/hello"


_DROPPED_CREATE_CASES: tuple[tuple[str, dict], ...] = (
    ("a tag creation", {"branch": "v1.0", "ref_type": "tag"}),
    ("a repository creation", {"branch": None, "ref_type": "repository"}),
    ("older than the window", {"created_at": _STALE}),
)


@pytest.mark.parametrize(("label", "overrides"), _DROPPED_CREATE_CASES)
def test_a_creation_failing_a_keep_filter_is_dropped(label, overrides):
    event = _create_event(**overrides)

    pairs = _pushed_pairs_of([[event]], NOW)

    assert pairs == [], label


def test_a_malformed_event_beside_a_good_one_is_skipped_without_losing_the_good_one():
    junk = {"type": "PushEvent"}
    good = _push_event()

    pairs = _pushed_pairs_of([[junk, good]], NOW)

    assert [pair.branch for pair in pairs] == ["feature-branch"]


def test_a_qualifying_event_becomes_a_push_pair():
    event = _push_event(
        repo="octocat/hello", branch="fix/loader-race", created_at="2026-08-18T12:00:00Z"
    )

    pairs = _pushed_pairs_of([[event]], NOW)

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.repository == "octocat/hello"
    assert pair.branch == "fix/loader-race"
    assert pair.pushed_at == datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def test_a_duplicate_pair_collapses_to_the_newest_push():
    older = _create_event(created_at="2026-08-14T00:00:00Z")
    newer = _push_event(created_at="2026-08-19T00:00:00Z")

    pairs = _pushed_pairs_of([[older, newer]], NOW)

    assert len(pairs) == 1
    assert pairs[0].pushed_at == datetime(2026, 8, 19, tzinfo=UTC)


def test_pairs_are_capped_at_max_pairs():
    """The discovery cap is wider than the display cap, so pairs qualification will discard
    cannot crowd out fresh branches.
    """
    events: list[object] = [
        _push_event(branch=f"branch-{index}", created_at="2026-08-19T00:00:00Z")
        for index in range(MAX_PAIRS + 5)
    ]

    pairs = _pushed_pairs_of([events], NOW)

    assert len(pairs) == MAX_PAIRS


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


# --- Escaping ---


def test_a_hostile_branch_name_round_trips_through_the_transport():
    event = _recent_push_event(branch='fix/"weird"\\branch')
    repository = _qualified_repository()

    http = graphql_http(events=[event], pushed=_qualification_payload(repository))
    result = query_pushed_branches(CREDENTIALS, http)

    assert result.unavailable is False
    assert [branch.branch for branch in result.branches] == ['fix/"weird"\\branch']


# --- Ordering ---


def test_two_branches_come_back_newest_push_first():
    older = _push_event(
        branch="old", created_at=(datetime.now(UTC) - timedelta(days=5)).isoformat()
    )
    newer = _push_event(
        branch="new", created_at=(datetime.now(UTC) - timedelta(days=1)).isoformat()
    )
    qualification = _qualification_payload(_qualified_repository(), _qualified_repository())

    http = graphql_http(events=[newer, older], pushed=qualification)
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
        lambda: graphql_http(events_status=500),
        lambda: graphql_http(events=b"not json"),
        lambda: graphql_http(events=[_recent_push_event()], pushed_status=403),
        lambda: graphql_http(events=[_recent_push_event()], pushed=b"not json"),
    ],
)
def test_a_shape_or_transport_surprise_degrades_to_unavailable(http_factory):
    result = query_pushed_branches(CREDENTIALS, http_factory())

    assert result.unavailable is True
    assert result.branches == ()


def _http_forbidding_graphql() -> httpx.Client:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url == "https://api.github.com/user":
            return httpx.Response(200, json={"login": "octocat"})
        if request.url.path.startswith("/users/octocat/events"):
            return httpx.Response(200, json=[])
        raise AssertionError("no GraphQL request should be made when there are no pairs")

    return httpx.Client(transport=httpx.MockTransport(respond))


def test_zero_pairs_returns_an_available_empty_container_without_a_graphql_call():
    result = query_pushed_branches(CREDENTIALS, _http_forbidding_graphql())

    assert result.unavailable is False
    assert result.branches == ()

"""Tests for the GitHub source's list fetch: category precedence and semantics, item shape,
sanitization, and the translation of failures into IntegrationError, for both PyGithub's
REST search and the authored GraphQL search.
"""

from datetime import UTC, datetime

import httpx
import pytest

from smorg.core.contract import AccessNotAllowed, AuthExpired, Malformed, Unavailable
from smorg.integrations.github.source import Category, fetch
from smorg.integrations.github.source.search import (
    BASE_QUERY,
    MAX_PER_QUERY,
    QUERIES,
    _authored_pull_request_of,
    _category_of,
)

from .recorded import CREDENTIALS, HELLO, SEARCH, graphql_http, only_pull_requests

TOOLS = SEARCH["items"][1]


def _authored_node(
    number: int = 42,
    title: str = "Tidy the loader",
    repo: str = "octocat/hello",
    decision: str | None = None,
    rollup: str | None = None,
    draft: bool = False,
    updated_at: str = "2026-08-13T12:00:00Z",
    author: str | None = "octocat",
) -> dict:
    """A GraphQL authored-search node, shaped like the live query's response."""
    author_field: dict | None = None
    if author is not None:
        author_field = {"login": author}
    rollup_field: dict | None = None
    if rollup is not None:
        rollup_field = {"state": rollup}
    return {
        "number": number,
        "title": title,
        "url": f"https://github.com/{repo}/pull/{number}",
        "updatedAt": updated_at,
        "isDraft": draft,
        "reviewDecision": decision,
        "repository": {"nameWithOwner": repo},
        "author": author_field,
        "commits": {"nodes": [{"commit": {"statusCheckRollup": rollup_field}}]},
    }


def _authored_http(*nodes: dict) -> httpx.Client:
    return graphql_http(authored={"data": {"search": {"nodes": list(nodes)}}})


# --- What gets asked for ---


def test_every_declared_category_is_searched_for(github):
    fetch(CREDENTIALS, graphql_http())

    asked = set(github.searches)
    for _, qualifiers in QUERIES:
        assert f"{BASE_QUERY} {qualifiers}" in asked


def test_every_category_the_panel_draws_can_be_produced():
    """Together the queries and _category_of must cover every Category, or a section in
    the tab would always stay empty."""
    from_queries = {category for category, _ in QUERIES}
    from_authored = {
        _category_of(is_draft, decision, rollup)
        for is_draft in (True, False)
        for decision in (None, "APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED")
        for rollup in (None, "SUCCESS", "FAILURE", "PENDING")
    }
    assert from_queries | from_authored == set(Category)


def test_a_search_names_no_repository_so_the_whole_account_is_covered(github):
    fetch(CREDENTIALS, graphql_http())

    assert all("repo:" not in query for query in github.searches)


# --- Which bucket a review-requested pull request lands in ---


def test_a_pull_request_keeps_the_first_category_that_claimed_it(github):
    """Both review queries match a directly-requested review; the direct one
    runs first, so the tab shows it once, on the row that is actually true."""
    github.searching("user-review-requested:@me", [HELLO])
    github.searching("review-requested:@me", [HELLO])

    pulls = only_pull_requests(fetch(CREDENTIALS, graphql_http()))

    assert [pull.category for pull in pulls] == [Category.NEEDS_YOUR_REVIEW]


def test_a_team_request_is_whatever_the_direct_query_did_not_claim(github):
    """`review-requested:@me` is a superset covering both kinds; subtracting
    the direct ones by precedence is what leaves the team's."""
    github.searching("user-review-requested:@me", [HELLO])
    github.searching("review-requested:@me", [HELLO, TOOLS])

    by_id = {pr.id: pr.category for pr in only_pull_requests(fetch(CREDENTIALS, graphql_http()))}

    assert by_id["octocat/hello#42"] is Category.NEEDS_YOUR_REVIEW
    assert by_id["octocat/tools#7"] is Category.NEEDS_TEAM_REVIEW


def test_a_team_requested_pull_request_that_is_also_authored_keeps_the_team_bucket(github):
    github.searching("review-requested:@me", [HELLO])
    authored = _authored_node(
        number=42, repo="octocat/hello", decision="APPROVED", rollup="SUCCESS"
    )

    pulls = only_pull_requests(fetch(CREDENTIALS, _authored_http(authored)))

    assert [pull.category for pull in pulls] == [Category.NEEDS_TEAM_REVIEW]


# --- The authored category rule, row by row ---


_CATEGORY_TABLE: tuple[tuple[bool, str | None, str | None, Category], ...] = (
    (False, "APPROVED", "SUCCESS", Category.READY_TO_MERGE),
    (False, "APPROVED", "PENDING", Category.WAITING),
    (False, "APPROVED", "FAILURE", Category.NEEDS_ACTION),
    (False, "APPROVED", "ERROR", Category.NEEDS_ACTION),
    (False, "CHANGES_REQUESTED", "SUCCESS", Category.NEEDS_ACTION),
    (True, None, "FAILURE", Category.DRAFT),
    (False, "REVIEW_REQUIRED", "SUCCESS", Category.WAITING),
    (False, None, "SUCCESS", Category.READY_TO_MERGE),
    (False, "APPROVED", None, Category.READY_TO_MERGE),
    (False, None, None, Category.READY_TO_MERGE),
    (False, None, "EXPECTED", Category.WAITING),
)


@pytest.mark.parametrize(
    ("is_draft", "review_decision", "rollup_state", "expected"), _CATEGORY_TABLE
)
def test_category_of_matches_the_design_docs_scenario_table(
    is_draft, review_decision, rollup_state, expected
):
    assert _category_of(is_draft, review_decision, rollup_state) is expected


def test_an_authored_pull_request_lands_in_the_bucket_category_of_says(github):
    changes_requested = _authored_node(
        number=1, repo="octocat/needs-action", decision="CHANGES_REQUESTED"
    )
    ready = _authored_node(number=2, repo="octocat/ready", decision="APPROVED", rollup="SUCCESS")

    pulls = only_pull_requests(fetch(CREDENTIALS, _authored_http(changes_requested, ready)))
    by_id = {pull.id: pull.category for pull in pulls}

    assert by_id["octocat/needs-action#1"] is _category_of(False, "CHANGES_REQUESTED", None)
    assert by_id["octocat/ready#2"] is _category_of(False, "APPROVED", "SUCCESS")


def test_a_failing_check_is_something_to_act_on(github):
    node = _authored_node(rollup="FAILURE")

    pulls = only_pull_requests(fetch(CREDENTIALS, _authored_http(node)))

    assert [pull.category for pull in pulls] == [Category.NEEDS_ACTION]


# --- What an item carries ---


def test_an_item_is_identified_by_repository_and_number(github):
    """Unique across every repository in the tab and stable across refreshes,
    which is what the seen-state keys off."""
    github.searching("user-review-requested:@me", [HELLO])

    assert only_pull_requests(fetch(CREDENTIALS, graphql_http()))[0].id == "octocat/hello#42"


def test_an_item_carries_what_the_panel_draws(github):
    github.searching("user-review-requested:@me", [HELLO])

    pull = only_pull_requests(fetch(CREDENTIALS, graphql_http()))[0]

    assert pull.repository == "octocat/hello"
    assert pull.number == 42
    assert pull.title == "Tidy the loader"
    assert pull.author == "octocat"
    assert pull.url == "https://github.com/octocat/hello/pull/42"
    assert pull.updated_at == datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def test_an_authored_item_carries_what_the_panel_draws():
    node = _authored_node(
        number=42,
        title="Tidy the loader",
        repo="octocat/hello",
        updated_at="2026-08-13T12:00:00Z",
    )

    pull = _authored_pull_request_of(node)

    assert pull.id == "octocat/hello#42"
    assert pull.repository == "octocat/hello"
    assert pull.number == 42
    assert pull.title == "Tidy the loader"
    assert pull.author == "octocat"
    assert pull.url == "https://github.com/octocat/hello/pull/42"
    assert pull.updated_at == datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def test_pull_requests_come_back_newest_first(github):
    github.searching("user-review-requested:@me", [TOOLS, HELLO])

    pulls = only_pull_requests(fetch(CREDENTIALS, graphql_http()))

    assert [pull.id for pull in pulls] == ["octocat/hello#42", "octocat/tools#7"]


def test_authored_nodes_and_rest_results_merge_and_sort_newest_first(github):
    github.searching("user-review-requested:@me", [TOOLS])
    older = _authored_node(number=1, repo="octocat/old", updated_at="2026-08-01T00:00:00Z")
    newer = _authored_node(number=2, repo="octocat/new", updated_at="2026-08-20T00:00:00Z")

    pulls = only_pull_requests(fetch(CREDENTIALS, _authored_http(older, newer)))

    assert [pull.id for pull in pulls] == ["octocat/new#2", "octocat/tools#7", "octocat/old#1"]


def test_a_title_carrying_terminal_escapes_is_sanitised(github):
    """A pull request title is somebody else's text arriving at a terminal."""
    hostile = HELLO | {"title": "Tidy\x1b[31m the\x00 loader"}
    github.searching("user-review-requested:@me", [hostile])

    title = only_pull_requests(fetch(CREDENTIALS, graphql_http()))[0].title

    assert "\x1b" not in title
    assert "\x00" not in title


def test_an_authored_node_title_carrying_terminal_escapes_is_sanitised():
    hostile = _authored_node(title="Tidy\x1b[31m the\x00 loader")

    title = _authored_pull_request_of(hostile).title

    assert "\x1b" not in title
    assert "\x00" not in title


def test_a_deleted_author_leaves_the_row_drawable(github):
    github.searching("user-review-requested:@me", [HELLO | {"user": None}])

    assert only_pull_requests(fetch(CREDENTIALS, graphql_http()))[0].author == ""


def test_an_authored_node_with_no_author_leaves_the_row_drawable():
    node = _authored_node(author=None)

    assert _authored_pull_request_of(node).author == ""


def test_the_search_stops_at_the_bound(github):
    """A dashboard is not a backlog viewer; unbounded paging would keep a
    refresh going for as long as the account has pull requests."""
    many = [HELLO | {"number": index, "id": index} for index in range(MAX_PER_QUERY + 20)]
    github.searching("user-review-requested:@me", many)

    assert len(only_pull_requests(fetch(CREDENTIALS, graphql_http()))) == MAX_PER_QUERY


# --- Authored node parsing: tolerant fields degrade, required fields don't ---


def test_a_missing_review_decision_degrades_to_none():
    node = _authored_node()
    del node["reviewDecision"]

    assert _authored_pull_request_of(node).category == Category.READY_TO_MERGE


def test_a_non_boolean_is_draft_degrades_to_false():
    node = _authored_node(draft=True)
    node["isDraft"] = "yes"

    assert _authored_pull_request_of(node).category != Category.DRAFT


def test_a_missing_commits_chain_degrades_to_no_rollup():
    """A PR with no checks reports no rollup at all; that must read as normal, not malformed."""
    node = _authored_node()
    del node["commits"]

    assert _authored_pull_request_of(node).category == Category.READY_TO_MERGE


def test_a_node_that_is_not_an_object_is_malformed():
    with pytest.raises(Malformed):
        _authored_pull_request_of("not a node")


def test_a_node_missing_a_title_is_malformed():
    node = _authored_node()
    del node["title"]

    with pytest.raises(Malformed):
        _authored_pull_request_of(node)


def test_a_node_missing_an_updated_at_is_malformed():
    node = _authored_node()
    del node["updatedAt"]

    with pytest.raises(Malformed):
        _authored_pull_request_of(node)


def test_a_node_with_an_unparseable_updated_at_is_malformed():
    node = _authored_node(updated_at="not-a-timestamp")

    with pytest.raises(Malformed):
        _authored_pull_request_of(node)


def test_a_node_missing_a_repository_is_malformed():
    node = _authored_node()
    del node["repository"]

    with pytest.raises(Malformed):
        _authored_pull_request_of(node)


# --- Failures cross the seam as one of the three: REST search ---


def test_a_rejected_token_is_auth_expired(github):
    github.failing_every_search(401, {"message": "Bad credentials"})

    with pytest.raises(AuthExpired):
        fetch(CREDENTIALS, graphql_http())


def test_a_token_missing_a_scope_is_access_not_allowed(github):
    """A 403 is a scope or an SSO policy, not a blip: the token authenticated,
    so replacing it is not the fix and the tab must not say it expired."""
    github.failing_every_search(
        403, {"message": "Resource not accessible by personal access token"}
    )

    with pytest.raises(AccessNotAllowed):
        fetch(CREDENTIALS, graphql_http())


def test_an_sso_blocked_token_does_not_read_as_expired(github):
    """A token an organization's SSO refuses works everywhere else, so
    "expired or revoked" would send the reader to replace a token that is fine."""
    github.failing_every_search(
        403, {"message": "Resource protected by organization SAML enforcement"}
    )

    with pytest.raises(AccessNotAllowed) as raised:
        fetch(CREDENTIALS, graphql_http())

    message = str(raised.value)
    assert "organization" in message
    assert "expired" not in message


def test_a_refused_query_is_malformed(github):
    """422 means a qualifier this build wrote moved under us — the tab is
    broken, and stale data would promise a recovery that is not coming."""
    github.failing_every_search(422, {"message": "Validation Failed"})

    with pytest.raises(Malformed):
        fetch(CREDENTIALS, graphql_http())


def test_github_being_down_is_unavailable(github):
    github.failing_every_search(503, {"message": "Service unavailable"})

    with pytest.raises(Unavailable):
        fetch(CREDENTIALS, graphql_http())


def test_a_result_naming_no_repository_is_malformed(github):
    github.searching("user-review-requested:@me", [HELLO | {"repository_url": "nonsense"}])

    with pytest.raises(Malformed):
        fetch(CREDENTIALS, graphql_http())


def test_a_failure_never_repeats_the_token(github):
    github.failing_every_search(401, {"message": "Bad credentials"})

    with pytest.raises(AuthExpired) as raised:
        fetch(CREDENTIALS, graphql_http())

    assert "github_pat_secret" not in str(raised.value)


def test_an_expired_token_says_so_where_the_shell_appends_the_fix(github):
    """The shell appends "run: smorg connect github" to this; the message has
    to be the half that explains why."""
    github.failing_every_search(401, {"message": "Bad credentials"})

    with pytest.raises(AuthExpired) as raised:
        fetch(CREDENTIALS, graphql_http())

    assert "expired" in str(raised.value)


# --- Failures cross the seam as one of the three: authored GraphQL search ---


def test_an_authored_search_rejected_token_is_auth_expired(github):
    http = graphql_http(authored={"message": "Bad credentials"}, authored_status=401)

    with pytest.raises(AuthExpired):
        fetch(CREDENTIALS, http)


def test_an_authored_search_token_missing_a_scope_is_access_not_allowed(github):
    http = graphql_http(
        authored={"message": "Resource not accessible by personal access token"},
        authored_status=403,
    )

    with pytest.raises(AccessNotAllowed):
        fetch(CREDENTIALS, http)


def test_an_authored_search_server_error_is_unavailable(github):
    http = graphql_http(authored={"message": "Internal Server Error"}, authored_status=500)

    with pytest.raises(Unavailable):
        fetch(CREDENTIALS, http)


def test_an_unreachable_authored_search_is_unavailable(github):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    http = httpx.Client(transport=httpx.MockTransport(refuse))

    with pytest.raises(Unavailable) as raised:
        fetch(CREDENTIALS, http)

    assert "could not reach GitHub" in str(raised.value)


def test_unparseable_authored_json_is_malformed(github):
    http = graphql_http(authored=b"not json")

    with pytest.raises(Malformed):
        fetch(CREDENTIALS, http)


def test_a_missing_search_nodes_list_is_malformed(github):
    http = graphql_http(authored={"data": {"search": {}}})

    with pytest.raises(Malformed):
        fetch(CREDENTIALS, http)


def test_an_authored_node_missing_a_number_is_malformed(github):
    node = _authored_node()
    del node["number"]

    with pytest.raises(Malformed):
        fetch(CREDENTIALS, _authored_http(node))


def test_an_sso_blocked_authored_search_does_not_read_as_expired(github):
    http = graphql_http(
        authored={"message": "Resource protected by organization SAML enforcement"},
        authored_status=403,
    )

    with pytest.raises(AccessNotAllowed) as raised:
        fetch(CREDENTIALS, http)

    message = str(raised.value)
    assert "organization" in message
    assert "expired" not in message


def test_an_insufficient_scopes_refusal_is_access_not_allowed(github):
    """GitHub reports scope failures as HTTP 200 with a body-level errors list."""
    refusal = {"data": None, "errors": [{"type": "INSUFFICIENT_SCOPES", "message": "scopes"}]}

    with pytest.raises(AccessNotAllowed):
        fetch(CREDENTIALS, graphql_http(authored=refusal))


def test_a_graphql_rate_limit_refusal_is_unavailable(github):
    refusal = {"data": None, "errors": [{"type": "RATE_LIMITED", "message": "slow down"}]}

    with pytest.raises(Unavailable) as raised:
        fetch(CREDENTIALS, graphql_http(authored=refusal))

    assert "rate limit" in str(raised.value)


def test_an_unknown_graphql_refusal_is_unavailable_not_malformed(github):
    """An unknown error type must surface as unavailable, not as a broken tab."""
    refusal = {"data": None, "errors": [{"type": "SOMETHING_NEW", "message": "boom"}]}

    with pytest.raises(Unavailable) as raised:
        fetch(CREDENTIALS, graphql_http(authored=refusal))

    assert "boom" in str(raised.value)


def test_errors_beside_usable_data_do_not_discard_the_results(github):
    node = _authored_node()
    partial = {
        "data": {"search": {"nodes": [node]}},
        "errors": [{"type": "FORBIDDEN", "message": "one field was off limits"}],
    }

    pulls = only_pull_requests(fetch(CREDENTIALS, graphql_http(authored=partial)))

    assert [pull.id for pull in pulls] == ["octocat/hello#42"]

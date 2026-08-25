"""Tests for the GitHub source's list fetch: category precedence, item shape, sanitization,
and the translation of PyGithub's failures into IntegrationError.
"""

from datetime import UTC, datetime

import pytest

from smorg.core.contract import AccessNotAllowed, AuthExpired, Malformed, Unavailable
from smorg.integrations.github.source import Category, fetch
from smorg.integrations.github.source.search import BASE_QUERY, MAX_PER_QUERY, QUERIES

from .recorded import CREDENTIALS, HELLO, SEARCH, graphql_http, only_pull_requests

TOOLS = SEARCH["items"][1]


# --- What gets asked for ---


def test_every_declared_category_is_searched_for(github):
    fetch(CREDENTIALS, graphql_http())

    asked = set(github.searches)
    for _, qualifiers in QUERIES:
        assert f"{BASE_QUERY} {qualifiers}" in asked


def test_every_category_the_panel_draws_can_be_produced(github):
    """The queries and the Category enum are declared apart; a category with no
    query behind it would leave an always-empty section in the tab."""
    assert {category for category, _ in QUERIES} == set(Category)


def test_a_search_names_no_repository_so_the_whole_account_is_covered(github):
    fetch(CREDENTIALS, graphql_http())

    assert all("repo:" not in query for query in github.searches)


# --- Which bucket a pull request lands in ---


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


def test_a_pull_request_waiting_on_you_outranks_the_catch_all(github):
    github.searching("author:@me draft:false review:changes_requested", [HELLO])
    github.searching("author:@me draft:false", [HELLO, TOOLS])

    by_id = {pr.id: pr.category for pr in only_pull_requests(fetch(CREDENTIALS, graphql_http()))}

    assert by_id["octocat/hello#42"] is Category.NEEDS_ACTION
    assert by_id["octocat/tools#7"] is Category.WAITING


def test_a_failing_check_is_something_to_act_on(github):
    github.searching("author:@me draft:false status:failure", [HELLO])

    pulls = only_pull_requests(fetch(CREDENTIALS, graphql_http()))

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


def test_pull_requests_come_back_newest_first(github):
    github.searching("user-review-requested:@me", [TOOLS, HELLO])

    pulls = only_pull_requests(fetch(CREDENTIALS, graphql_http()))

    assert [pull.id for pull in pulls] == ["octocat/hello#42", "octocat/tools#7"]


def test_a_title_carrying_terminal_escapes_is_sanitised(github):
    """A pull request title is somebody else's text arriving at a terminal."""
    hostile = HELLO | {"title": "Tidy\x1b[31m the\x00 loader"}
    github.searching("user-review-requested:@me", [hostile])

    title = only_pull_requests(fetch(CREDENTIALS, graphql_http()))[0].title

    assert "\x1b" not in title
    assert "\x00" not in title


def test_a_deleted_author_leaves_the_row_drawable(github):
    github.searching("user-review-requested:@me", [HELLO | {"user": None}])

    assert only_pull_requests(fetch(CREDENTIALS, graphql_http()))[0].author == ""


def test_the_search_stops_at_the_bound(github):
    """A dashboard is not a backlog viewer; unbounded paging would keep a
    refresh going for as long as the account has pull requests."""
    many = [HELLO | {"number": index, "id": index} for index in range(MAX_PER_QUERY + 20)]
    github.searching("user-review-requested:@me", many)

    assert len(only_pull_requests(fetch(CREDENTIALS, graphql_http()))) == MAX_PER_QUERY


# --- Failures cross the seam as one of the three ---


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

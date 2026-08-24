"""Tests for the GitHub source.

No network. PyGithub's own connection-class seam serves recorded payloads, so
everything under test — the queries issued, the mapping to items, and the
translation of failures — runs through the real client rather than a stand-in
for it.
"""

import json
import urllib.parse
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from github.Requester import (
    HTTPRequestsConnectionClass,
    HTTPSRequestsConnectionClass,
    Requester,
    RequestsResponse,
)

from smorg.auth.store import Credentials
from smorg.core.contract import AccessNotAllowed, AuthExpired, Malformed, Unavailable
from smorg.integrations.github.source import (
    ABSENT_COUNT,
    BASE_QUERY,
    CHECK_RUNS_FETCH_LIMIT,
    COMMENTS_FETCH_LIMIT,
    MAX_PER_QUERY,
    PROFILE_ID,
    QUERIES,
    Category,
    ContributionWeek,
    Profile,
    PullRequest,
    fetch,
    fetch_detail,
)

FIXTURES = Path(__file__).parent / "fixtures"
SEARCH = json.loads((FIXTURES / "github_search.json").read_text())
PULL = json.loads((FIXTURES / "github_pull.json").read_text())
REVIEWS = json.loads((FIXTURES / "github_reviews.json").read_text())

HELLO = SEARCH["items"][0]
TOOLS = SEARCH["items"][1]

CREDENTIALS = Credentials(
    access_token="github_pat_secret", refresh_token=None, expires_at=None, scope=""
)

VIEWER = {
    "data": {
        "viewer": {
            "login": "octocat",
            "contributionsCollection": {
                "contributionCalendar": {
                    "totalContributions": 204,
                    "weeks": [
                        {
                            "firstDay": "2026-08-09",
                            "contributionDays": [
                                {"weekday": 0, "contributionLevel": "NONE"},
                                {"weekday": 1, "contributionLevel": "FIRST_QUARTILE"},
                                {"weekday": 2, "contributionLevel": "SECOND_QUARTILE"},
                                {"weekday": 3, "contributionLevel": "THIRD_QUARTILE"},
                                {"weekday": 4, "contributionLevel": "FOURTH_QUARTILE"},
                                {"weekday": 5, "contributionLevel": "NONE"},
                                {"weekday": 6, "contributionLevel": "NONE"},
                            ],
                        },
                        {
                            "firstDay": "2026-08-16",
                            "contributionDays": [
                                {"weekday": 0, "contributionLevel": "FOURTH_QUARTILE"},
                            ],
                        },
                    ],
                }
            },
        }
    }
}


def graphql_http(body: object = None, status: int = 200) -> httpx.Client:
    if body is None:
        body = VIEWER

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.github.com/graphql"
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(respond))


def failing_http() -> httpx.Client:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    return httpx.Client(transport=httpx.MockTransport(refuse))


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError("PyGithub brings its own transport; fetch_detail's client must go unused")


# Handed to fetch_detail calls, and wired to fail if anything ever reaches it: PyGithub owns
# that path's transport, so the shell's shared client has nothing to do there.
UNUSED_HTTP = httpx.Client(transport=httpx.MockTransport(_refuse))


def only_pull_requests(items: tuple) -> list[PullRequest]:
    return [item for item in items if isinstance(item, PullRequest)]


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


class _Recorded(RequestsResponse):
    """One recorded answer: an HTTP status and a JSON body.

    Subclasses the response type PyGithub's connection returns, so a change to
    what it has to provide shows up as a type error rather than at runtime.
    """

    def __init__(self, status: int, body: object) -> None:
        self.status = status
        self.headers = {"content-type": "application/json"}
        self._body = json.dumps(body)

    def getheaders(self):
        return self.headers.items()

    def read(self) -> str:
        return self._body

    def raise_for_status(self) -> None:
        """Never raises: a recorded error status is answered rather than
        thrown, so the source sees what a real error response looks like."""


class _Server:
    """Recorded answers keyed by what was asked for, and a log of the asking.

    Search results are registered per query string, so a test says which
    category a pull request came back under by registering it against that
    category's query and nothing else.
    """

    def __init__(self) -> None:
        self.searches: list[str] = []
        self.paths: list[str] = []
        self._by_query: dict[str, tuple[int, object]] = {}
        self._by_path: dict[str, tuple[int, object]] = {}

    def searching(self, qualifiers: str, items: list[dict], status: int = 200) -> None:
        body = {"total_count": len(items), "incomplete_results": False, "items": items}
        self._by_query[f"{BASE_QUERY} {qualifiers}"] = (status, body)

    def failing_every_search(self, status: int, body: object) -> None:
        for _, qualifiers in QUERIES:
            self._by_query[f"{BASE_QUERY} {qualifiers}"] = (status, body)

    def serving(self, path: str, body: object, status: int = 200) -> None:
        self._by_path[path] = (status, body)

    def answer(self, url: str) -> _Recorded:
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parts.query).get("q", [""])[0]
        self.paths.append(parts.path)
        if query:
            self.searches.append(query)
            status, body = self._by_query.get(
                query, (200, {"total_count": 0, "incomplete_results": False, "items": []})
            )
            return _Recorded(status, body)
        status, body = self._by_path[parts.path]
        return _Recorded(status, body)


_LIVE: list[_Server] = []


class _Answering:
    """Answers every request from the live _Server instead of a network.

    Mixed into both connection classes PyGithub injects: https is the one the
    client uses, and http is stubbed too so nothing can quietly fall through to
    a real socket. Nothing of the parent is initialised — opening a session is
    the one thing this must not do.
    """

    def __init__(self, host: str, port: int | None = None, **kwargs: object) -> None:
        self._url = ""

    def request(self, verb, url, input, headers, stream=False) -> None:
        self._url = url

    def getresponse(self) -> _Recorded:
        return _LIVE[0].answer(self._url)

    def close(self) -> None:
        pass


class _HttpsConnection(_Answering, HTTPSRequestsConnectionClass):
    pass


class _HttpConnection(_Answering, HTTPRequestsConnectionClass):
    pass


@pytest.fixture
def github():
    server = _Server()
    _LIVE.append(server)
    Requester.injectConnectionClasses(_HttpConnection, _HttpsConnection)
    try:
        yield server
    finally:
        Requester.resetConnectionClasses()
        _LIVE.clear()


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


# --- The viewer's profile and contribution calendar ---


def test_the_profile_arrives_last_with_parsed_weeks(github):
    items = fetch(CREDENTIALS, graphql_http())

    profile = items[-1]
    assert isinstance(profile, Profile)
    assert profile.id == PROFILE_ID
    assert profile.login == "octocat"
    assert profile.url == "https://github.com/octocat"
    assert profile.total_contributions == 204
    assert profile.unavailable is False
    assert isinstance(profile.weeks[0], ContributionWeek)
    assert profile.weeks[0].first_day == date(2026, 8, 9)
    assert profile.weeks[0].levels == (0, 1, 2, 3, 4, 0, 0)
    assert profile.weeks[1].first_day == date(2026, 8, 16)
    # The partial trailing week fills unqueried days with ABSENT_DAY.
    assert profile.weeks[1].levels == (4, -1, -1, -1, -1, -1, -1)


def test_a_failing_graphql_call_degrades_to_an_unavailable_profile(github):
    items = fetch(CREDENTIALS, failing_http())

    profile = items[-1]
    assert isinstance(profile, Profile)
    assert profile.unavailable is True
    # No searches were registered, so the pull-request half must be empty, not broken.
    assert only_pull_requests(items) == []


def test_a_graphql_error_status_degrades_to_an_unavailable_profile(github):
    items = fetch(CREDENTIALS, graphql_http({"message": "no"}, status=403))

    assert isinstance(items[-1], Profile) and items[-1].unavailable is True


def test_a_misshapen_graphql_payload_degrades_instead_of_raising(github):
    items = fetch(CREDENTIALS, graphql_http({"data": {"viewer": "what"}}))

    assert isinstance(items[-1], Profile) and items[-1].unavailable is True


def test_a_misshapen_week_start_degrades_to_an_unavailable_profile(github):
    """A parse failure in the calendar must not cost the pull-request half of the fetch."""
    github.searching("user-review-requested:@me", [HELLO])
    hostile = json.loads(json.dumps(VIEWER))
    calendar = hostile["data"]["viewer"]["contributionsCollection"]["contributionCalendar"]
    calendar["weeks"][0]["firstDay"] = 5

    items = fetch(CREDENTIALS, graphql_http(hostile))

    assert isinstance(items[-1], Profile) and items[-1].unavailable is True
    assert [pull.id for pull in only_pull_requests(items)] == ["octocat/hello#42"]


def test_an_empty_login_degrades_to_an_unavailable_profile(github):
    github.searching("user-review-requested:@me", [HELLO])
    hostile = json.loads(json.dumps(VIEWER))
    hostile["data"]["viewer"]["login"] = ""

    items = fetch(CREDENTIALS, graphql_http(hostile))

    assert isinstance(items[-1], Profile) and items[-1].unavailable is True
    assert [pull.id for pull in only_pull_requests(items)] == ["octocat/hello#42"]


def test_the_profile_login_is_sanitized(github):
    hostile = json.loads(json.dumps(VIEWER))
    hostile["data"]["viewer"]["login"] = "octo\x1b[31mcat"

    profile = fetch(CREDENTIALS, graphql_http(hostile))[-1]

    assert isinstance(profile, Profile)
    assert "\x1b" not in profile.login


# --- The pull request detail ---


def test_detail_carries_the_body_the_branches_and_the_reviews(github):
    serving_detail(github, reviews=REVIEWS)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert "Splits the loader in two." in detail.body
    assert detail.base == "main"
    assert detail.head == "tidy-loader"
    assert [review.author for review in detail.reviews] == ["hubot", "monalisa"]
    assert [review.state for review in detail.reviews] == ["CHANGES_REQUESTED", "APPROVED"]


def test_detail_costs_one_request_per_thing_it_shows(github):
    """The repository is addressed by name and never read, so it is not
    fetched — a detail pane that cost three requests to open would make the
    key that opens it feel like a page load."""
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

    assert detail.additions == 128
    assert detail.deletions == 41
    assert detail.changed_files == 6


def test_missing_line_counts_read_as_absent_not_zero(github):
    hostile = PULL | {"additions": None, "deletions": "nan", "changed_files": None}
    serving_detail(github, pull=hostile)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert detail.additions == ABSENT_COUNT
    assert detail.deletions == ABSENT_COUNT
    assert detail.changed_files == ABSENT_COUNT


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

    assert [comment.author for comment in detail.comments] == ["alice", "bob"]
    assert detail.comments[0].body == "Looks good but the retry cap seems low."
    assert detail.hidden_comments == 0


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

    assert [comment.body for comment in detail.comments] == ["c4", "c5", "c6", "c7", "c8"]
    assert detail.hidden_comments == 4
    assert detail.hidden_comments_is_lower_bound is False


def test_a_comment_list_at_the_cap_reads_as_a_lower_bound(github):
    many = [
        {"user": {"login": "who"}, "body": f"c{index}", "created_at": "2026-08-13T10:00:00Z"}
        for index in range(COMMENTS_FETCH_LIMIT)
    ]
    serving_detail(github, comments=many)

    detail = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM)

    assert detail.hidden_comments_is_lower_bound is True


def test_a_comment_survives_a_deleted_account_and_a_hostile_body(github):
    hostile = [{"user": None, "body": "hi\x1b[31m", "created_at": "2026-08-13T10:00:00Z"}]
    serving_detail(github, comments=hostile)

    comment = fetch_detail(CREDENTIALS, UNUSED_HTTP, ITEM).comments[0]

    assert comment.author == ""
    assert "\x1b" not in comment.body

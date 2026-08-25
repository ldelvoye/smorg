"""Tests for the GitHub source's viewer profile: the contribution calendar and its GraphQL
failure modes.
"""

import json
from datetime import date

import httpx
import pytest

from smorg.core.contract import Unavailable
from smorg.integrations.github.source import PROFILE_ID, ContributionWeek, Profile, fetch

from .recorded import CREDENTIALS, HELLO, VIEWER, graphql_http, only_pull_requests


def failing_http() -> httpx.Client:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    return httpx.Client(transport=httpx.MockTransport(refuse))


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


def test_a_totally_unreachable_graphql_endpoint_stops_the_fetch(github):
    """An unreachable endpoint fails the authored search too, which raises: the tab must
    error rather than render an inbox missing its authored half.
    """
    with pytest.raises(Unavailable):
        fetch(CREDENTIALS, failing_http())


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

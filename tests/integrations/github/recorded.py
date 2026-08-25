"""A recorded GitHub server: canned search, GraphQL, and REST answers that PyGithub and httpx
are pointed at instead of the network.
"""

import json
import urllib.parse
from pathlib import Path

import httpx
from github.Requester import (
    HTTPRequestsConnectionClass,
    HTTPSRequestsConnectionClass,
    RequestsResponse,
)

from smorg.auth.store import Credentials
from smorg.integrations.github.source import PullRequest
from smorg.integrations.github.source.search import BASE_QUERY, QUERIES

FIXTURES = Path(__file__).parent / "fixtures"
SEARCH = json.loads((FIXTURES / "github_search.json").read_text())

HELLO = SEARCH["items"][0]

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


def graphql_http(
    body: object = None,
    status: int = 200,
    authored: object = None,
    authored_status: int = 200,
) -> httpx.Client:
    """A GraphQL client routed by query text: an authored search ("search(" in the query)
    gets `authored`/`authored_status`, anything else (the viewer query) gets
    `body`/`status`. Bytes for `authored` simulate an unparseable response.
    """
    if body is None:
        body = VIEWER
    if authored is None:
        authored = {"data": {"search": {"nodes": []}}}

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.github.com/graphql"
        payload = json.loads(request.content)
        query = payload.get("query", "")
        if "search(" in query:
            if isinstance(authored, bytes):
                return httpx.Response(authored_status, content=authored)
            return httpx.Response(authored_status, json=authored)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(respond))


def only_pull_requests(items: tuple) -> list[PullRequest]:
    return [item for item in items if isinstance(item, PullRequest)]


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

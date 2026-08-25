"""PyGithub client construction and the seam that turns its failures into IntegrationError."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import requests
from github import (
    Auth,
    BadAttributeException,
    BadCredentialsException,
    Github,
    GithubException,
    RateLimitExceededException,
)
from github.GithubObject import GithubObject
from github.PaginatedList import PaginatedList

from smorg.auth.store import Credentials
from smorg.core.contract import (
    AccessNotAllowed,
    AuthExpired,
    IntegrationError,
    Malformed,
    Unavailable,
)
from smorg.core.text import sanitize_line

REQUEST_TIMEOUT_SECONDS = 30
RESULTS_PER_PAGE = 50
MAX_RETRIES = 2

# How GitHub names an organization that requires SSO, in the body of its 403.
SAML_ENFORCEMENT = "saml enforcement"


def _message_of(error: GithubException) -> str:
    """The server's own explanation, when it sent a readable one."""
    data = error.data
    if not isinstance(data, dict):
        return ""
    message = data.get("message")
    if not isinstance(message, str):
        return ""
    return message


def _translated(error: GithubException) -> IntegrationError:
    """The IntegrationError matching what would fix the failure: a new token (401), access
    granted (403), a corrected query (422), or waiting (any other status).
    """
    if error.status == 401:
        return AuthExpired("GitHub rejected the stored token; it may have expired or been revoked")
    if error.status == 403:
        if SAML_ENFORCEMENT in _message_of(error).casefold():
            return AccessNotAllowed("the token is not authorized for this organization's SSO")
        return AccessNotAllowed(
            "the token cannot reach this repository; check its organization access and scopes"
        )
    if error.status == 422:
        # GitHub refused a query this app wrote.
        return Malformed(f"GitHub refused the search: {sanitize_line(_message_of(error))}")
    return Unavailable(f"GitHub returned HTTP {error.status}")


@contextmanager
def github_errors() -> Iterator[None]:
    """Turn everything PyGithub and its transport raise into IntegrationError."""
    try:
        yield
    except BadCredentialsException as error:
        raise AuthExpired(
            "GitHub rejected the stored token; it may have expired or been revoked"
        ) from error
    except RateLimitExceededException as error:
        raise Unavailable("GitHub's rate limit is exhausted; it resets shortly") from error
    except BadAttributeException as error:
        raise Malformed(f"GitHub returned a field of an unexpected type: {error}") from error
    except GithubException as error:
        raise _translated(error) from error
    except requests.RequestException as error:
        raise Unavailable("could not reach GitHub") from error


def connect(credentials: Credentials, lazy: bool = False) -> Github:
    """A client for one call into GitHub.

    `lazy` stops an object built from an address it was handed from fetching its own payload
    before anything reads it. That is how fetch_detail addresses a repository by name without
    paying a request for it.
    """
    return Github(
        auth=Auth.Token(credentials.access_token),
        timeout=REQUEST_TIMEOUT_SECONDS,
        per_page=RESULTS_PER_PAGE,
        retry=MAX_RETRIES,
        lazy=lazy,
        # PyGithub paces every request by default, which GitHub asks for between writes. This
        # integration doesn't write, and writes keep their own separate pacing regardless.
        seconds_between_requests=0,
    )


def first[T: GithubObject](results: PaginatedList[T], limit: int) -> list[T]:
    """Up to `limit` results. A PaginatedList pages as it is walked, so stopping the walk is
    what stops the paging.
    """
    found: list[T] = []
    for result in results:
        found.append(result)
        if len(found) >= limit:
            break
    return found

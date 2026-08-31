"""The tab's item assembly: one query per item kind, composed in display order."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from smorg.auth.store import Credentials
from smorg.core.contract import Item
from smorg.integrations.github.source.profile import query_profile
from smorg.integrations.github.source.pushed import query_pushed_branches
from smorg.integrations.github.source.search import query_prs

FETCH_PHASES = ("pull requests", "profile", "pushed branches")


def fetch_with_progress(
    credentials: Credentials, http: httpx.Client, report: Callable[[int], None]
) -> tuple[Item, ...]:
    """Every item the GitHub tab shows, calling report(index) as each FETCH_PHASES entry
    begins: the pull requests, then the profile, then the pushed branches.
    """
    report(0)
    prs = query_prs(credentials, http)
    report(1)
    profile = query_profile(credentials, http)
    report(2)
    pushed_branches = query_pushed_branches(credentials, http)
    items: list[Item] = list(prs)
    items.append(profile)
    items.append(pushed_branches)
    return tuple(items)


def fetch(credentials: Credentials, http: httpx.Client) -> tuple[Item, ...]:
    """Every item the GitHub tab shows, with no progress reporting."""

    def ignore(index: int) -> None:
        return None

    return fetch_with_progress(credentials, http, ignore)

"""The tab's item assembly: one query per item kind, composed in display order."""

from __future__ import annotations

import httpx

from smorg.auth.store import Credentials
from smorg.core.contract import Item
from smorg.integrations.github.source.profile import query_profile
from smorg.integrations.github.source.pushed import query_pushed_branches
from smorg.integrations.github.source.search import query_prs


def fetch(credentials: Credentials, http: httpx.Client) -> tuple[Item, ...]:
    """Every item the GitHub tab shows: the pull requests, then the profile, then the pushed
    branches.
    """
    prs = query_prs(credentials, http)
    profile = query_profile(credentials, http)
    pushed_branches = query_pushed_branches(credentials, http)
    items: list[Item] = list(prs)
    items.append(profile)
    items.append(pushed_branches)
    return tuple(items)

"""GitHub's declaration; connects with a personal access token and reads the REST API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

import httpx

from smorg.auth.store import Credentials
from smorg.auth.token import TokenMethod
from smorg.core.contract import Action, ActionClass, AuthPath, Item, Manifest
from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.github.source import (
    FETCH_PHASES,
    DiffRequest,
    PullRequestDetail,
    PullRequestDiff,
    fetch,
    fetch_detail,
    fetch_diff,
    fetch_with_progress,
)

TOKEN = TokenMethod(
    label="GitHub personal access token",
    help_url="https://github.com/settings/personal-access-tokens",
    scopes_hint=(
        "read access to Pull requests and Metadata (fine-grained), "
        "or repo:all and read:org scopes (classic)"
    ),
)

MANIFEST = Manifest(
    id="github",
    display_name="GitHub",
    connections=(AuthPath(id="token", method=TOKEN),),
    # Keep above 5min to avoid rate limiting
    stale_after=timedelta(minutes=5),
    actions=(Action(id="open", label="Open in GitHub", key="o", action_class=ActionClass.LAUNCH),),
)


@dataclass(frozen=True)
class GitHubIntegration:
    manifest: Manifest = MANIFEST
    panel_class: type[GitHubPanel] = GitHubPanel
    fetch_phases: tuple[str, ...] = FETCH_PHASES

    def fetch(self, credentials: Credentials, http: httpx.Client) -> tuple[Item, ...]:
        return fetch(credentials, http)

    def fetch_with_progress(
        self, credentials: Credentials, http: httpx.Client, report: Callable[[int], None]
    ) -> tuple[Item, ...]:
        return fetch_with_progress(credentials, http, report)

    def fetch_detail(
        self, credentials: Credentials, http: httpx.Client, item: Item
    ) -> PullRequestDetail | PullRequestDiff:
        if isinstance(item, DiffRequest):
            return fetch_diff(credentials, http, item)
        return fetch_detail(credentials, http, item)


INTEGRATION = GitHubIntegration()

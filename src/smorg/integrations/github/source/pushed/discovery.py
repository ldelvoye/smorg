"""Which repositories the viewer might have pushed to recently: owned plus contributed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from smorg.auth.store import Credentials
from smorg.integrations.github.source.client import query_graphql
from smorg.integrations.github.source.pushed.qualification import WINDOW

# pushedAt reflects anyone's push, so this query over-selects busy org repos; the tier cache
# is what keeps their steady-state cost down.
_DISCOVERY_QUERY = """
query {
  viewer {
    login
    repositories(
      first: 50
      orderBy: {field: PUSHED_AT, direction: DESC}
      affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
    ) {
      nodes { nameWithOwner pushedAt }
    }
    repositoriesContributedTo(
      first: 50
      contributionTypes: [COMMIT]
      orderBy: {field: PUSHED_AT, direction: DESC}
    ) {
      nodes { nameWithOwner pushedAt }
    }
  }
}
"""


@dataclass(frozen=True)
class CandidateRepo:
    name: str
    pushed_at: datetime


def _candidate_of(raw_node: object, now: datetime) -> CandidateRepo | None:
    if not isinstance(raw_node, dict):
        return None
    name = raw_node.get("nameWithOwner")
    if not isinstance(name, str) or "/" not in name:
        return None
    raw_pushed_at = raw_node.get("pushedAt")
    if not isinstance(raw_pushed_at, str):
        return None
    try:
        pushed_at = datetime.fromisoformat(raw_pushed_at)
    except ValueError:
        return None
    if pushed_at.tzinfo is None:
        return None
    if now - pushed_at > WINDOW:
        return None
    return CandidateRepo(name=name, pushed_at=pushed_at)


def _nodes_of(raw_viewer: dict, field: str) -> list[object] | None:
    connection = raw_viewer.get(field)
    if not isinstance(connection, dict):
        return None
    nodes = connection.get("nodes")
    if not isinstance(nodes, list):
        return None
    return nodes


def discover_repos(
    credentials: Credentials, http: httpx.Client, now: datetime
) -> tuple[str, list[CandidateRepo]] | None:
    """The viewer login and every repo worth an activity lookup, in source order, deduped;
    None on any failure.
    """
    try:
        response = query_graphql(credentials, http, _DISCOVERY_QUERY)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    viewer = data.get("viewer")
    if not isinstance(viewer, dict):
        return None
    login = viewer.get("login")
    if not isinstance(login, str):
        return None
    owned = _nodes_of(viewer, "repositories")
    contributed = _nodes_of(viewer, "repositoriesContributedTo")
    if owned is None or contributed is None:
        return None
    candidates: list[CandidateRepo] = []
    seen: set[str] = set()
    for raw_node in owned + contributed:
        candidate = _candidate_of(raw_node, now)
        if candidate is None:
            continue
        if candidate.name in seen:
            continue
        seen.add(candidate.name)
        candidates.append(candidate)
    return login, candidates

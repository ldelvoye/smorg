"""Fetch one pull request's file-by-file diff and map it to typed items."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from github import BadAttributeException
from github.File import File as GithubFile

from smorg.auth.store import Credentials
from smorg.core.contract import Item, Malformed
from smorg.core.text import sanitize_block, sanitize_line, truncate
from smorg.integrations.github.source.client import connect, first, github_errors
from smorg.integrations.github.source.detail import ABSENT_COUNT
from smorg.integrations.github.source.search import PullRequest

FILES_FETCH_LIMIT = 100
PATCH_LIMIT = 20_000


@dataclass(frozen=True)
class FileDiff:
    path: str
    previous_path: str
    status: str
    additions: int
    deletions: int
    patch: str


@dataclass(frozen=True)
class PullRequestDiff:
    files: tuple[FileDiff, ...]
    truncated: bool


@dataclass(frozen=True)
class DiffRequest(Item):
    pull_request: PullRequest


def diff_request_of(pr: PullRequest) -> DiffRequest:
    return DiffRequest(id=f"{pr.id}/diff", updated_at=pr.updated_at, url=pr.url, pull_request=pr)


def fetch_diff(credentials: Credentials, http: httpx.Client, item: Item) -> PullRequestDiff:
    """The selected pull request's file-by-file diff: each file's status, line counts, and
    patch text.
    """
    if not isinstance(item, DiffRequest):
        raise Malformed(f"expected a diff request, got {type(item).__name__}")
    pr = item.pull_request
    with connect(credentials, lazy=True) as client, github_errors():
        repository = client.get_repo(pr.repository)
        pull_request = repository.get_pull(pr.number)
        raw_files = first(pull_request.get_files(), FILES_FETCH_LIMIT)
        files = [_file_of(raw) for raw in raw_files]
        return PullRequestDiff(files=tuple(files), truncated=len(raw_files) >= FILES_FETCH_LIMIT)


def _file_of(raw: GithubFile) -> FileDiff:
    filename = raw.filename
    if isinstance(filename, str):
        path = sanitize_line(filename)
    else:
        path = ""
    previous_filename = raw.previous_filename
    if isinstance(previous_filename, str):
        previous_path = sanitize_line(previous_filename)
    else:
        previous_path = ""
    status = raw.status
    if isinstance(status, str):
        file_status = status
    else:
        file_status = ""
    additions, deletions = _counts_of(raw)
    patch = raw.patch
    if isinstance(patch, str):
        file_patch = truncate(sanitize_block(patch, limit=None), PATCH_LIMIT)
    else:
        file_patch = ""
    return FileDiff(
        path=path,
        previous_path=previous_path,
        status=file_status,
        additions=additions,
        deletions=deletions,
        patch=file_patch,
    )


def _counts_of(raw: GithubFile) -> tuple[int, int]:
    try:
        additions = raw.additions
        deletions = raw.deletions
    except BadAttributeException:
        return ABSENT_COUNT, ABSENT_COUNT
    return _count_of(additions), _count_of(deletions)


def _count_of(value: object) -> int:
    if not isinstance(value, int) or value < 0:
        return ABSENT_COUNT
    return value

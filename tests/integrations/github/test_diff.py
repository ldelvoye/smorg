"""Tests for the GitHub diff source: per-file mapping and the diff request's cache key."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import cast

from github.File import File as GithubFile

from smorg.core.text import truncate
from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.github.source import ABSENT_COUNT
from smorg.integrations.github.source.diff import PATCH_LIMIT, _file_of, diff_request_of

from .helpers import pull


def _fake_file(**fields: object) -> GithubFile:
    return cast(GithubFile, SimpleNamespace(**fields))


def test_file_mapping_degrades_field_by_field():
    renamed = _fake_file(
        filename="new.py",
        previous_filename="old.py",
        additions=3,
        deletions=1,
        patch=None,
    )
    mapped_rename = _file_of(renamed)
    assert mapped_rename.previous_path == "old.py"
    assert mapped_rename.patch == ""

    misshapen_counts = _fake_file(
        filename="a.py",
        previous_filename=None,
        additions="nope",
        deletions=None,
        patch="+x",
    )
    mapped_counts = _file_of(misshapen_counts)
    assert mapped_counts.additions == ABSENT_COUNT
    assert mapped_counts.deletions == ABSENT_COUNT
    assert mapped_counts.previous_path == ""

    hostile = _fake_file(
        filename="one\x1b[31mtwo.py",
        previous_filename=None,
        additions=1,
        deletions=1,
        patch="one\x1b[31mtwo",
    )
    mapped_hostile = _file_of(hostile)
    assert "\x1b" not in mapped_hostile.path
    assert "\x1b" not in mapped_hostile.patch

    long_patch = _fake_file(
        filename="big.py",
        previous_filename=None,
        additions=1,
        deletions=1,
        patch="x" * (PATCH_LIMIT + 500),
    )
    mapped_long = _file_of(long_patch)
    assert mapped_long.patch == truncate("x" * (PATCH_LIMIT + 500), PATCH_LIMIT)


def test_diff_request_key_differs_from_the_prs_own_but_moves_with_its_version():
    pr = pull(42)
    request = diff_request_of(pr)

    assert request.id == f"{pr.id}/diff"
    assert request.updated_at == pr.updated_at
    assert GitHubPanel.detail_key(request) != GitHubPanel.detail_key(pr)

    newer_pr = replace(pr, updated_at=pr.updated_at + timedelta(hours=1))
    newer_request = diff_request_of(newer_pr)
    assert GitHubPanel.detail_key(newer_request) != GitHubPanel.detail_key(request)

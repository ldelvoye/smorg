"""Tests for the pushed-branches activity cache: round-trip and tolerant load."""

from datetime import UTC, datetime

from smorg.integrations.github.source.pushed.state import ActivityCache
from smorg.integrations.github.source.pushed.tiers import RepoRecord

STAMP = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def test_a_cache_round_trips_through_its_file(tmp_path):
    path = tmp_path / "github-activity.json"
    cache = ActivityCache.load(path)
    cache.records["octocat/hello"] = RepoRecord(last_activity=STAMP, last_probed=STAMP)
    cache.records["octocat/quiet"] = RepoRecord(last_activity=None, last_probed=STAMP)
    cache.cursor = "octocat/hello"
    cache.save()

    reloaded = ActivityCache.load(path)

    assert reloaded.records == cache.records
    assert reloaded.cursor == "octocat/hello"


def test_a_corrupt_or_missing_file_starts_an_empty_cache(tmp_path):
    missing = ActivityCache.load(tmp_path / "absent.json")
    assert missing.records == {}

    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("not json")
    corrupt = ActivityCache.load(corrupt_path)
    assert corrupt.records == {}
    assert corrupt.cursor is None


def test_a_malformed_record_is_dropped_without_losing_the_rest(tmp_path):
    path = tmp_path / "github-activity.json"
    path.write_text(
        '{"repos": {"octocat/bad": {"last_activity": 5, "last_probed": "nope"},'
        ' "octocat/good": {"last_activity": null, "last_probed": "2026-08-28T12:00:00+00:00"}},'
        ' "cursor": null}'
    )

    cache = ActivityCache.load(path)

    assert list(cache.records) == ["octocat/good"]

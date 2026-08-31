"""Tests for pushed-branches tiering: who gets an activity call on a given refresh."""

from datetime import UTC, datetime, timedelta

from smorg.integrations.github.source.pushed.activity import HOT_TIME_PERIOD, PROBE_TIME_PERIOD
from smorg.integrations.github.source.pushed.qualification import WINDOW
from smorg.integrations.github.source.pushed.tiers import (
    RETIREMENT,
    RepoRecord,
    observed,
    plan_refresh,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def _record(active_days_ago: int | None, probed_days_ago: int = 1) -> RepoRecord:
    if active_days_ago is None:
        last_activity = None
    else:
        last_activity = NOW - timedelta(days=active_days_ago)
    last_probed = NOW - timedelta(days=probed_days_ago)
    return RepoRecord(last_activity=last_activity, last_probed=last_probed)


def test_tier_boundaries_pick_each_repo_treatment():
    """Hot at exactly the window edge, cold just past it, retired past the horizon or when
    a probe proved the viewer never active."""
    records = {
        "octocat/hot-edge": _record(WINDOW.days),
        "octocat/cold": _record(WINDOW.days + 1),
        "octocat/retired": _record(RETIREMENT.days + 1, probed_days_ago=2),
        "octocat/proven-never": _record(None),
    }
    candidates = list(records) + ["octocat/unknown"]

    plan = plan_refresh(candidates, records, None, NOW)

    calls = dict(plan.calls)
    assert calls["octocat/hot-edge"] == HOT_TIME_PERIOD
    assert calls["octocat/cold"] == PROBE_TIME_PERIOD
    assert calls["octocat/unknown"] == PROBE_TIME_PERIOD
    assert calls["octocat/retired"] == PROBE_TIME_PERIOD
    assert "octocat/proven-never" not in calls


def test_the_oldest_retired_repo_gets_one_probe_per_refresh():
    """Retirement is recoverable without the feed: the band rotates at one probe per refresh."""
    records = {
        "octocat/hot": _record(0),
        "octocat/retired-a": _record(RETIREMENT.days + 1, probed_days_ago=3),
        "octocat/retired-b": _record(RETIREMENT.days + 1, probed_days_ago=5),
        "octocat/proven-never": _record(None, probed_days_ago=10),
    }

    plan = plan_refresh(list(records), records, None, NOW)

    calls = dict(plan.calls)
    assert calls["octocat/hot"] == HOT_TIME_PERIOD
    assert calls["octocat/proven-never"] == PROBE_TIME_PERIOD
    assert "octocat/retired-a" not in calls
    assert "octocat/retired-b" not in calls
    assert len(calls) == 2


def test_cold_probes_take_a_fifth_rounded_up():
    records = {f"octocat/cold-{index}": _record(40) for index in range(6)}

    plan = plan_refresh(list(records), records, None, NOW)

    probed = [repo for repo, period in plan.calls if period == PROBE_TIME_PERIOD]
    assert len(probed) == 2


def test_a_single_cold_repo_is_still_probed():
    records = {"octocat/only-cold": _record(40)}

    plan = plan_refresh(list(records), records, None, NOW)

    assert plan.calls == (("octocat/only-cold", PROBE_TIME_PERIOD),)


def test_the_rotation_resumes_after_the_cursor_and_wraps():
    records = {f"octocat/cold-{index}": _record(40) for index in range(5)}

    first = plan_refresh(list(records), records, None, NOW)
    second = plan_refresh(list(records), records, first.cursor, NOW)

    first_probed = [repo for repo, _ in first.calls]
    second_probed = [repo for repo, _ in second.calls]
    assert first_probed == ["octocat/cold-0"]
    assert second_probed == ["octocat/cold-1"]
    assert first.cursor == "octocat/cold-0"


def test_the_rotation_resumes_when_the_cursor_repo_left_the_cold_band():
    """A probed repo that woke back to hot must not reset the rotation to the start."""
    records = {f"octocat/cold-{index}": _record(40) for index in range(5) if index != 1}
    candidates = list(records)

    plan = plan_refresh(candidates, records, "octocat/cold-1", NOW)

    probed = [repo for repo, period in plan.calls if period == PROBE_TIME_PERIOD]
    assert probed == ["octocat/cold-2"]


def test_observed_keeps_the_old_stamp_when_a_probe_finds_nothing():
    record = _record(40)

    updated = observed(record, None, NOW)

    assert updated.last_activity == record.last_activity
    assert updated.last_probed == NOW


def test_observed_advances_to_the_newest_pair():
    updated = observed(None, NOW - timedelta(days=2), NOW)

    assert updated.last_activity == NOW - timedelta(days=2)
    assert updated.last_probed == NOW

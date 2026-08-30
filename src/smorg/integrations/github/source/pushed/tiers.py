"""Which repositories get an activity call on a refresh: hot every time, cold in rotation,
retired never."""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from smorg.integrations.github.source.pushed.activity import HOT_TIME_PERIOD, PROBE_TIME_PERIOD
from smorg.integrations.github.source.pushed.qualification import WINDOW

RETIREMENT = timedelta(days=90)
COLD_PROBE_RATIO = 0.2


@dataclass(frozen=True)
class RepoRecord:
    """What the cache knows about one repository: the viewer's newest observed activity, and
    when it was last asked."""

    last_activity: datetime | None
    last_probed: datetime | None


@dataclass(frozen=True)
class RefreshPlan:
    calls: tuple[tuple[str, str], ...]
    cursor: str | None


def _probe_rotation(cold: list[str], cursor: str | None) -> list[str]:
    if not cold:
        return []
    count = math.ceil(COLD_PROBE_RATIO * len(cold))
    ordered = sorted(cold)
    if cursor is None:
        start = 0
    else:
        start = bisect.bisect_right(ordered, cursor)
    rotated = ordered[start:] + ordered[:start]
    return rotated[:count]


def plan_refresh(
    candidates: list[str],
    records: dict[str, RepoRecord],
    cursor: str | None,
    now: datetime,
) -> RefreshPlan:
    """One refresh's activity calls: every hot repo, plus a fifth of the cold band."""
    hot: list[str] = []
    cold: list[str] = []
    unknown: list[str] = []
    for name in candidates:
        record = records.get(name)
        if record is None or record.last_probed is None:
            unknown.append(name)
            continue
        if record.last_activity is None:
            continue
        age = now - record.last_activity
        if age <= WINDOW:
            hot.append(name)
        elif age <= RETIREMENT:
            cold.append(name)
    probes = _probe_rotation(cold, cursor)
    calls: list[tuple[str, str]] = []
    for name in hot:
        calls.append((name, HOT_TIME_PERIOD))
    for name in unknown:
        calls.append((name, PROBE_TIME_PERIOD))
    for name in probes:
        calls.append((name, PROBE_TIME_PERIOD))
    if probes:
        next_cursor = probes[-1]
    else:
        next_cursor = cursor
    return RefreshPlan(calls=tuple(calls), cursor=next_cursor)


def observed(record: RepoRecord | None, pairs_newest: datetime | None, now: datetime) -> RepoRecord:
    """The record after an activity response: the stamp advances only on evidence."""
    if record is None:
        previous = None
    else:
        previous = record.last_activity
    if pairs_newest is None:
        last_activity = previous
    elif previous is None or pairs_newest > previous:
        last_activity = pairs_newest
    else:
        last_activity = previous
    return RepoRecord(last_activity=last_activity, last_probed=now)

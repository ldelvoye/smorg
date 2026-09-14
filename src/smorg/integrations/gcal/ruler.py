"""Laying a day's timed events onto rows: the one walk the day and week views both draw from."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from smorg.integrations.gcal.source import Event

SLOT_MINUTES = 15
SLOTS_PER_DAY = 96
MAX_LANES = 3


@dataclass(frozen=True)
class Placed:
    event: Event
    first_slot: int
    slot_count: int
    lane: int
    lane_count: int


@dataclass(frozen=True)
class Row:
    slot: int
    time: datetime
    hour_rule: bool


@dataclass(frozen=True)
class Layout:
    start: datetime
    rows: tuple[Row, ...]
    placed: tuple[Placed, ...]
    hidden: tuple[Event, ...]
    now_row: int | None


def _timed_on(events: tuple[Event, ...], day: date, zone: tzinfo) -> list[Event]:
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    day_end = day_start + timedelta(days=1)
    timed = [
        event
        for event in events
        if not event.all_day and event.start < day_end and event.end > day_start
    ]
    timed.sort(key=lambda event: (event.start, event.end))
    return timed


def _slot_of(moment: datetime, start: datetime) -> int:
    elapsed_minutes = (moment - start).total_seconds() / 60
    slot = math.floor(elapsed_minutes / SLOT_MINUTES)
    return slot


def _assign_lanes(spans: list[tuple[int, int, Event]]) -> tuple[list[Placed], list[Event]]:
    """Greedy interval partitioning over slot ranges; a cluster's width is its widest overlap."""
    lane_ends: list[int] = []
    assigned: list[tuple[int, int, int, Event]] = []
    hidden: list[Event] = []
    for first, count, event in spans:
        last = first + count
        lane = None
        for index, lane_end in enumerate(lane_ends):
            if lane_end <= first:
                lane = index
                break
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(last)
        else:
            lane_ends[lane] = last
        if lane >= MAX_LANES:
            hidden.append(event)
            continue
        assigned.append((first, count, lane, event))

    placed: list[Placed] = []
    for first, count, lane, event in assigned:
        last = first + count
        overlapping_lanes = {
            other_lane
            for other_first, other_count, other_lane, _ in assigned
            if other_first < last and other_first + other_count > first
        }
        lane_count = max(overlapping_lanes) + 1
        placed.append(
            Placed(
                event=event,
                first_slot=first,
                slot_count=count,
                lane=lane,
                lane_count=lane_count,
            )
        )
    return placed, hidden


def lay_out(events: tuple[Event, ...], day: date, zone: tzinfo, now: datetime) -> Layout:
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    timed = _timed_on(events, day, zone)

    spans: list[tuple[int, int, Event]] = []
    for event in timed:
        start_slot = _slot_of(event.start, start)
        first_slot = max(0, start_slot)
        elapsed_minutes = (event.end - start).total_seconds() / 60
        end_slot = math.ceil(elapsed_minutes / SLOT_MINUTES)
        last_slot = min(SLOTS_PER_DAY, end_slot)
        slot_count = max(1, last_slot - first_slot)
        spans.append((first_slot, slot_count, event))
    placed, hidden = _assign_lanes(spans)

    if now.date() == day:
        now_row = _slot_of(now, start)
    else:
        now_row = None

    rows: list[Row] = []
    for slot in range(SLOTS_PER_DAY):
        offset = timedelta(minutes=slot * SLOT_MINUTES)
        time = start + offset
        hour_rule = time.minute == 0
        rows.append(Row(slot=slot, time=time, hour_rule=hour_rule))

    return Layout(
        start=start,
        rows=tuple(rows),
        placed=tuple(placed),
        hidden=tuple(hidden),
        now_row=now_row,
    )

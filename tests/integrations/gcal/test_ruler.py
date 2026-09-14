from datetime import timedelta

from smorg.integrations.gcal.ruler import MAX_LANES, lay_out

from .helpers import NOW, PACIFIC, at, event


def test_the_full_day_lays_out_96_quarter_hour_rows():
    events = (
        event("early", at(0, 6, 45), at(0, 7, 15)),
        event("odd", at(0, 12, 15), at(0, 12, 45)),
        event("late", at(0, 19, 30), at(0, 21, 0)),
    )

    layout = lay_out(events, NOW.date(), PACIFIC, NOW)

    assert len(layout.rows) == 96
    assert layout.rows[0].time == at(0, 0)
    assert layout.rows[95].time == at(0, 23, 45)
    by_id = {placed.event.id: placed for placed in layout.placed}
    assert by_id["early"].first_slot == 27
    assert by_id["odd"].first_slot == 49
    assert layout.rows[49].hour_rule is False
    assert by_id["late"].first_slot == 78


def test_a_short_event_still_gets_one_slot_and_the_now_line_lands_on_its_row():
    events = (event("a", at(0, 11, 41), at(0, 11, 44)),)

    layout = lay_out(events, NOW.date(), PACIFIC, NOW)

    placed = layout.placed[0]
    assert placed.slot_count == 1
    assert layout.now_row == 46
    assert placed.first_slot == layout.now_row


def test_the_now_line_is_absent_on_another_day():
    events = (event("a", at(1, 9), at(1, 9, 30)),)
    layout = lay_out(events, NOW.date() + timedelta(days=1), PACIFIC, NOW)
    assert layout.now_row is None


def test_overlaps_split_into_lanes_and_the_fourth_is_hidden():
    events = (
        event("a", at(0, 11), at(0, 12)),
        event("b", at(0, 11, 15), at(0, 11, 45)),
        event("c", at(0, 11, 30), at(0, 12, 30)),
        event("d", at(0, 11, 40), at(0, 13)),
        event("e", at(0, 15), at(0, 16)),
    )

    layout = lay_out(events, NOW.date(), PACIFIC, NOW)

    by_id = {placed.event.id: placed for placed in layout.placed}
    assert {by_id["a"].lane, by_id["b"].lane, by_id["c"].lane} == {0, 1, 2}
    assert by_id["a"].lane_count == MAX_LANES
    assert by_id["e"].lane_count == 1
    assert [hidden.id for hidden in layout.hidden] == ["d"]

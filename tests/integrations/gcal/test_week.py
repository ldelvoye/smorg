from datetime import date

import pytest
from rich.console import Group
from rich.style import Style
from rich.text import Text

from smorg.integrations.gcal.ruler import lay_out
from smorg.integrations.gcal.views import CalendarView
from smorg.integrations.gcal.views.day import RULER_GUTTER, CalendarDay
from smorg.integrations.gcal.views.week import CalendarWeek, column_count, visible_days
from smorg.shell.app import _format_binding_rows
from smorg.shell.format import plain_lines

from .helpers import PanelHarness, week_panel


def _text(view: CalendarWeek) -> str:
    return "\n".join(view.content_lines())


def test_column_count_steps_at_the_named_widths():
    widths = [80, 90, 110, 140, 200]
    counts = [column_count(width) for width in widths]
    assert counts == [1, 3, 5, 7, 7]


def test_visible_days_centres_on_the_focused_day_and_clamps_to_the_window():
    first = date(2026, 9, 14)
    last = date(2026, 9, 27)

    centred = visible_days(date(2026, 9, 16), first, last, 3)
    assert centred == (date(2026, 9, 15), date(2026, 9, 16), date(2026, 9, 17))

    slid_forward = visible_days(date(2026, 9, 14), first, last, 3)
    assert slid_forward == (date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16))

    workweek = visible_days(date(2026, 9, 18), first, last, 5)
    assert workweek[0] == date(2026, 9, 14)

    full_week = visible_days(date(2026, 9, 23), first, last, 7)
    assert full_week[0] == date(2026, 9, 21)

    sliding_saturday = visible_days(date(2026, 9, 19), first, last, 5)
    assert sliding_saturday == (
        date(2026, 9, 15),
        date(2026, 9, 16),
        date(2026, 9, 17),
        date(2026, 9, 18),
        date(2026, 9, 19),
    )

    sliding_sunday = visible_days(date(2026, 9, 20), first, last, 5)
    assert sliding_sunday[-1] == date(2026, 9, 20)


@pytest.mark.asyncio
async def test_the_week_view_draws_five_columns_with_a_hidden_weekend_indicator():
    panel = week_panel()
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        panel.show_view(CalendarView.WEEK)
        await pilot.pause()
        view = panel.query_one(CalendarWeek)
        width = view._ruler_width()
        assert column_count(width) == 5

        text = _text(view)
        assert "14◥" in text
        # a ~21-column cell truncates "Migration review: pk swap" before "review" completes.
        assert "Migration" in text
        assert "+1" in text
        assert "Farmers market" not in text
        assert text.count("11:42") == 1

        body_width = view.body_width()
        assert all(len(line) <= body_width for line in view.content_lines())

        header_lines = plain_lines(view._render_header(), body_width)
        assert len(header_lines) == 3
        assert all(len(line) <= body_width for line in header_lines)

        selected = view.selected_item()
        assert selected is not None
        assert selected.id == "design"

        column_widths = view._column_widths(width, 5)
        focused_start = RULER_GUTTER
        next_start = focused_start + column_widths[0] + 1
        ruler_group = view._render_ruler()
        assert isinstance(ruler_group, Group)
        rows = ruler_group.renderables
        row = rows[0]
        assert isinstance(row, Text)
        focused_tinted = any(
            span.start == focused_start and Style.parse(span.style).bgcolor is not None
            for span in row.spans
        )
        neighbour_tinted = any(
            span.start == next_start and Style.parse(span.style).bgcolor is not None
            for span in row.spans
        )
        assert focused_tinted
        assert not neighbour_tinted

        now_rows = [row for row in rows if isinstance(row, Text) and "11:42" in row.plain]
        assert len(now_rows) == 1
        now_row = now_rows[0]
        assert len(rows) == 96
        assert now_row.plain[focused_start] == "●"
        neighbour_chip_kept = any(
            span.start == next_start and Style.parse(span.style).bgcolor is not None
            for span in now_row.spans
        )
        assert neighbour_chip_kept


@pytest.mark.asyncio
async def test_keys_move_the_selection_the_focused_day_and_the_week():
    panel = week_panel()
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        panel.show_view(CalendarView.WEEK)
        await pilot.pause()
        view = panel.query_one(CalendarWeek)

        await pilot.press("down")
        await pilot.pause()
        selected = view.selected_item()
        assert selected is not None
        assert selected.id == "hours"

        focused = panel.focused()
        layout = lay_out(panel.events_on(focused), focused, panel.zone(), panel.now())
        by_id = {placed.event.id: placed for placed in layout.placed}
        hours = by_id["hours"]
        first_row = hours.first_slot
        ruler = view.query_one("#week-ruler")
        ruler_height = ruler.size.height
        scroll_y = view.ruler_scroll_y
        assert scroll_y <= first_row
        assert first_row + hours.slot_count <= scroll_y + ruler_height

        await pilot.press("right")
        await pilot.pause()
        assert panel.focused().day == 15
        selected = view.selected_item()
        assert selected is not None
        assert selected.id == "standup-tue"

        for _ in range(4):
            await pilot.press("right")
        await pilot.pause()
        assert panel.focused().day == 19

        numbers_line = view.content_lines()[1]
        assert "19" in numbers_line
        assert "14" not in numbers_line

        await pilot.press("right_square_bracket")
        await pilot.pause()
        assert panel.focused().day == 26

        await pilot.press("left_square_bracket")
        await pilot.pause()
        assert panel.focused().day == 19

        await pilot.press("t")
        await pilot.pause()
        assert panel.focused().day == 14

        await pilot.press("escape")
        assert panel.active_view is CalendarView.MENU


@pytest.mark.asyncio
async def test_a_narrow_terminal_shows_one_column():
    panel = week_panel()
    async with PanelHarness(panel).run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        panel.show_view(CalendarView.WEEK)
        await pilot.pause()
        view = panel.query_one(CalendarWeek)
        width = view._ruler_width()
        assert column_count(width) == 1

        text = _text(view)
        assert "14◥" in text

        ruler = view.query_one("#week-ruler")
        assert ruler.size.height >= 10


@pytest.mark.asyncio
async def test_paired_bindings_merge_into_one_help_row():
    panel = week_panel()
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        week_rows = _format_binding_rows(pilot.app, CalendarWeek.BINDINGS)
        day_rows = _format_binding_rows(pilot.app, CalendarDay.BINDINGS)

        assert ("←/→", "change day") in week_rows
        assert ("[/]", "change week") in week_rows
        assert ("⇧ + ↑/↓", "scroll an hour") in week_rows
        assert ("←/→", "change day") in day_rows
        assert ("⇧ + ↑/↓", "scroll an hour") in day_rows

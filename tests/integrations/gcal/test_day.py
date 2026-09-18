import pytest

from smorg.integrations.gcal.ruler import lay_out
from smorg.integrations.gcal.views import CalendarView
from smorg.integrations.gcal.views.day import CalendarDay
from smorg.shell.format import plain_lines

from .helpers import PanelHarness, week_panel


def _text(view: CalendarDay) -> str:
    return "\n".join(view.content_lines())


@pytest.mark.asyncio
async def test_the_day_view_draws_header_chips_now_line_and_footer():
    panel = week_panel()
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        panel.show_view(CalendarView.DAY)
        await pilot.pause()
        view = panel.query_one(CalendarDay)
        text = _text(view)
        assert "M" in text and "14" in text
        assert "Office" in text
        assert "Infra standup" in text
        assert "11:42" in text
        assert "Design sync: calendar tab" in text
        assert "coming with write permissions" not in text
        assert "12:30 Design sync: calendar tab" in text
        assert "14◥" in text
        assert "00:00" in text and "23:00" in text
        width = view.body_width()
        assert all(len(line) <= width for line in view.content_lines())

        body = view.query_one("#day-ruler-body")
        body_width = body.content_size.width
        ruler_group = view._render_ruler()
        ruler_lines = plain_lines(ruler_group, body_width)
        assert all(len(line) <= body_width for line in ruler_lines)


@pytest.mark.asyncio
async def test_entering_the_view_anchors_on_the_now_line():
    panel = week_panel()
    async with PanelHarness(panel).run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        panel.show_view(CalendarView.DAY)
        await pilot.pause()
        # on_show's call_after_refresh only runs on the next refresh cycle.
        await pilot.pause()
        view = panel.query_one(CalendarDay)
        ruler = view.query_one("#day-ruler")
        ruler_height = ruler.size.height
        anchor_scroll_y = view.ruler_scroll_y
        now_row = 46

        assert anchor_scroll_y <= now_row < anchor_scroll_y + ruler_height
        assert now_row - anchor_scroll_y < ruler_height / 2

        await pilot.press("shift+down")
        await pilot.press("shift+down")
        await pilot.pause()
        assert view.ruler_scroll_y == anchor_scroll_y + 8

        await pilot.press("t")
        await pilot.pause()
        assert view.ruler_scroll_y == anchor_scroll_y


@pytest.mark.asyncio
async def test_keys_move_the_selection_and_the_focused_day():
    panel = week_panel()
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        panel.show_view(CalendarView.DAY)
        await pilot.pause()
        view = panel.query_one(CalendarDay)
        selected = view.selected_item()
        assert selected is not None
        assert selected.id == "design"

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
        ruler = view.query_one("#day-ruler")
        ruler_height = ruler.size.height
        scroll_y = view.ruler_scroll_y
        assert scroll_y <= first_row
        assert first_row + hours.slot_count <= scroll_y + ruler_height

        await pilot.press("right")
        assert panel.focused().day == 15
        selected = view.selected_item()
        assert selected is not None
        assert selected.id == "standup-tue"
        assert "11:42" not in _text(view)

        await pilot.press("t")
        assert panel.focused().day == 14

        await pilot.press("escape")
        assert panel.active_view is CalendarView.MENU


@pytest.mark.asyncio
async def test_a_short_terminal_keeps_header_and_footer_pinned():
    panel = week_panel()
    async with PanelHarness(panel).run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        panel.show_view(CalendarView.DAY)
        await pilot.pause()
        view = panel.query_one(CalendarDay)
        text = _text(view)
        assert "14" in text
        assert "needs action" in text

        header = view.query_one("#day-header")
        footer = view.query_one("#day-footer")
        ruler = view.query_one("#day-ruler")
        expected_ruler_height = 24 - header.size.height - footer.size.height
        assert ruler.size.height == expected_ruler_height
        assert ruler.size.height >= 10

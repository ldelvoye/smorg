import pytest

from smorg.integrations.gcal.views import CalendarView
from smorg.integrations.gcal.views.menu import CalendarMenu, next_meeting_label

from .helpers import NOW, PanelHarness, at, calendars, event, panel_with, week_panel


def _text(menu: CalendarMenu) -> str:
    return "\n".join(menu.content_lines())


def test_the_countdown_has_three_shapes():
    today = event("a", at(0, 12, 30), at(0, 13))
    tomorrow = event("b", at(1, 9), at(1, 9, 30))
    later = event("c", at(3, 9), at(3, 9, 30))
    assert next_meeting_label(today, NOW) == "in 48 min"
    assert next_meeting_label(tomorrow, NOW) == "tomorrow · 09:00"
    assert next_meeting_label(later, NOW) == "Thu · 09:00"


def test_the_panel_picks_the_next_meeting_skipping_all_day_and_working_location():
    panel = week_panel()
    next_meeting = panel.next_meeting()
    assert next_meeting is not None
    assert next_meeting.id == "design"
    assert [invite.id for invite in panel.invites()] == ["design", "hours"]


@pytest.mark.asyncio
async def test_the_landing_shows_the_date_icon_countdown_dots_and_destinations(monkeypatch):
    panel = week_panel()
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        menu = panel.query_one(CalendarMenu)
        text = _text(menu)
        assert "Monday, September 14" in text
        assert "██" in text
        assert "Design sync: calendar tab" in text
        assert "in 48 min" in text
        assert "awaiting your reply" in text
        assert "●  ●  ●  ●" in text
        assert "▸ today" in text
        assert "invites awaiting your reply (2)" in text

        toasts: list[str] = []
        monkeypatch.setattr(menu, "notify", lambda message, **kwargs: toasts.append(message))
        await pilot.press("down", "enter")
        assert panel.active_view is CalendarView.MENU
        assert toasts == ["coming in the next milestone"]


@pytest.mark.asyncio
async def test_with_nothing_left_the_countdown_reaches_into_tomorrow():
    late = panel_with(calendars(), event("b", at(1, 9), at(1, 9, 30), "Standup"))
    late.now_provider = lambda: NOW.replace(hour=17, minute=30)
    async with PanelHarness(late).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert "tomorrow · 09:00" in _text(late.query_one(CalendarMenu))

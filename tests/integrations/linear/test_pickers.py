"""The Linear pickers: what they list, what they return, and the toasts when there is nothing."""

import pytest
from textual.widgets import Static

from smorg.integrations.linear.navigation import Target
from smorg.integrations.linear.source import ParentSummary, RelatedIssue, SubIssue
from smorg.integrations.linear.views.pickers import OpenFromPicker, TrailPicker

from .helpers import PanelHarness, detail, issue, panel_with


def _full_detail():
    return detail(
        parent=ParentSummary(id="ENG-0", title="epic", status="In Progress", status_type="started"),
        sub_issues=(
            SubIssue(id="ENG-2", title="a", status="Done", status_type="completed", priority=""),
        ),
        blocked_by=(RelatedIssue(id="ENG-5", title="c"),),
    )


@pytest.mark.asyncio
async def test_enter_opens_the_picker_and_choosing_a_row_opens_that_issue(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    panel = panel_with(issue("ENG-1"))
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        panel.show_detail(panel.detail_key(issue("ENG-1")), _full_detail())
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()
        picker = pilot.app.screen
        assert isinstance(picker, OpenFromPicker)
        lines = picker.content_lines()
        assert lines[0] == "parent"
        assert "sub-issues (1/1)" in lines and "blocked by (1)" in lines

        await pilot.press("down", "enter")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, OpenFromPicker)
        assert panel.trail_ids() == ("ENG-1", "ENG-2")
        assert panel.viewed is not None and panel.viewed.title == "a"


@pytest.mark.asyncio
async def test_enter_toasts_instead_of_opening_when_there_is_nothing_or_no_detail_yet(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    notified: list[str] = []
    monkeypatch.setattr(
        "smorg.integrations.linear.panel.LinearPanel.notify",
        lambda self, message, **kwargs: notified.append(message),
    )
    panel = panel_with(issue("ENG-1"))
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert notified == ["still loading"]

        panel.show_detail(panel.detail_key(issue("ENG-1")), detail())
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert notified == ["still loading", "nothing to open from here"]
        assert isinstance(pilot.app.screen.query_one("#reading-body"), Static)

    fresh_panel = panel_with(issue("ENG-1"))
    async with PanelHarness(fresh_panel).run_test(size=(120, 40)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        fresh_panel.show_detail_error(fresh_panel.detail_key(issue("ENG-1")), "linear is down")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert notified[-1] == "could not load"


@pytest.mark.asyncio
async def test_backspace_opens_the_trail_picker_preselected_on_the_previous_page(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    panel = panel_with(issue("ENG-1"))
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        panel.open_target(
            Target(
                id="ENG-2", title="b", status="Todo", status_type="unstarted", priority="", url=""
            )
        )
        await pilot.pause()

        await pilot.press("backspace")
        await pilot.pause()
        picker = pilot.app.screen
        assert isinstance(picker, TrailPicker)
        assert picker.selected_value() == 0
        lines = picker.content_lines()
        assert "ENG-2" in lines[0]
        trail_line = next(line for line in lines if line.startswith("▸ "))
        assert "ENG-1" in trail_line
        rows_only = [line for line in lines if line.strip() and "esc close" not in line]
        assert rows_only[-1].endswith("issues")

        await pilot.press("down", "enter")
        await pilot.pause()
        assert panel.trail_ids() == ()
        assert not isinstance(pilot.app.screen, TrailPicker)

"""Tests for the Linear host panel: view delegation, never the network."""

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Static

from smorg.integrations.linear.navigation import Target
from smorg.integrations.linear.views import LinearView
from smorg.integrations.linear.views.issue import LinearIssueView
from smorg.integrations.linear.views.issues import LinearIssues

from .helpers import PanelHarness, detail, issue, panel_with


@pytest.mark.asyncio
async def test_enter_opens_the_issue_view_marks_it_seen_and_requests_detail(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    panel = panel_with(issue("ENG-1"))
    requested: list = []
    original = type(panel).post_message

    def capture(message):
        if isinstance(message, panel.DetailRequested):
            requested.append(message)
        return original(panel, message)

    async with PanelHarness(panel).run_test() as pilot:
        panel.post_message = capture
        await pilot.pause()
        assert panel.seen.is_changed("linear", issue("ENG-1")) is True

        await pilot.press("enter")
        await pilot.pause()

        assert panel.active_view is LinearView.ISSUE
        assert panel.viewed == issue("ENG-1")
        assert panel.query_one(LinearIssueView).display is True
        assert panel.query_one(LinearIssues).display is False
        assert panel.seen.is_changed("linear", issue("ENG-1")) is False
        assert "\n".join(panel.query_one(LinearIssueView).content_lines()).count("loading") == 1

        await pilot.press("escape")
        await pilot.pause()

        assert panel.active_view is LinearView.ISSUES
        assert panel.viewed is None
        assert panel.query_one(LinearIssues).has_focus
    assert [message.item.id for message in requested] == ["ENG-1"]


@pytest.mark.asyncio
async def test_reopening_an_issue_whose_detail_failed_retries(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    panel = panel_with(issue("ENG-1"))
    requested: list = []
    original = type(panel).post_message

    def capture(message):
        if isinstance(message, panel.DetailRequested):
            requested.append(message)
        return original(panel, message)

    async with PanelHarness(panel).run_test() as pilot:
        panel.post_message = capture
        await pilot.press("enter")
        await pilot.pause()
        panel.show_detail_error(panel.detail_key(issue("ENG-1")), "linear is down")
        await pilot.pause()
        assert "could not load: linear is down" in "\n".join(
            panel.query_one(LinearIssueView).content_lines()
        )
        await pilot.press("escape")
        await pilot.press("enter")
        await pilot.pause()
    assert len(requested) == 2


def test_help_bindings_follow_the_active_view():
    panel = panel_with(issue("ENG-1"))
    assert panel.help_bindings() is LinearIssues.BINDINGS
    panel.active_view = LinearView.ISSUE
    assert panel.help_bindings() is LinearIssueView.BINDINGS


def _target(identifier: str) -> Target:
    return Target(
        id=identifier,
        title=f"title of {identifier}",
        status="Todo",
        status_type="unstarted",
        priority="",
        url=f"https://linear.app/x/issue/{identifier}",
    )


@pytest.mark.asyncio
async def test_opening_targets_grows_the_trail_and_escape_walks_it_back(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    panel = panel_with(issue("ENG-1"))
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        panel.open_target(_target("ENG-2"))
        await pilot.pause()
        panel.open_target(_target("ENG-1"))
        await pilot.pause()
        assert panel.trail_ids() == ("ENG-1", "ENG-2", "ENG-1")
        assert panel.viewed == issue("ENG-1")
        header = "\n".join(panel.query_one(LinearIssueView).content_lines())
        assert "‹ esc — ENG-2" in header
        assert "issues › ENG-1 › ENG-2 › ENG-1" in header

        await pilot.press("escape")
        await pilot.pause()
        assert panel.trail_ids() == ("ENG-1", "ENG-2")
        assert panel.viewed is not None and panel.viewed.id == "ENG-2"

        panel.go_back_to(-1)
        await pilot.pause()
        assert panel.trail_ids() == ()
        assert panel.active_view is LinearView.ISSUES
        assert panel.query_one(LinearIssues).has_focus


@pytest.mark.asyncio
async def test_the_breadcrumb_never_cuts_an_id_in_the_live_render(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    panel = panel_with(issue("INFRAPLAT-1001"))
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        panel.open_target(_target("INFRAPLAT-1002"))
        panel.open_target(_target("INFRAPLAT-1003"))
        await pilot.pause()
        body = panel.query_one("#reading-body", Static)
        first_line = body.render_line(0).text.rstrip()
        assert "…" not in first_line
        assert first_line.endswith("INFRAPLAT-1003")


@pytest.mark.asyncio
async def test_a_foreign_target_is_not_marked_seen_but_a_listed_one_is(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    panel = panel_with(issue("ENG-1"), issue("ENG-2"))
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        panel.open_target(_target("ENG-99"))
        await pilot.pause()
        assert panel.seen.is_changed("linear", issue("ENG-2")) is True
        panel.open_target(_target("ENG-2"))
        await pilot.pause()
        assert panel.seen.is_changed("linear", issue("ENG-2")) is False
    assert panel.viewed == issue("ENG-2")


@pytest.mark.asyncio
async def test_going_back_restores_the_previous_page_s_scroll(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    panel = panel_with(issue("ENG-1"))
    long_description = "\n\n".join(f"line {index}" for index in range(120))
    async with PanelHarness(panel).run_test(size=(120, 30)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        panel.show_detail(panel.detail_key(issue("ENG-1")), detail(description=long_description))
        await pilot.pause()
        reading = panel.query_one("#reading", VerticalScroll)
        reading.scroll_to(y=9, animate=False)
        await pilot.pause()
        panel.open_target(_target("ENG-2"))
        await pilot.pause()
        assert panel.query_one("#reading", VerticalScroll).scroll_offset.y == 0
        await pilot.press("escape")
        await pilot.pause()
        assert panel.query_one("#reading", VerticalScroll).scroll_offset.y == 9

"""Tests for the Linear host panel: view delegation, never the network."""

from pathlib import Path

import pytest

from smorg.integrations.linear.views import LinearView
from smorg.integrations.linear.views.issue import LinearIssueView
from smorg.integrations.linear.views.issues import LinearIssues

from .helpers import PanelHarness, issue, panel_with


def test_the_panel_and_its_views_never_fetch():
    """The seam the whole design rests on, enforced rather than trusted."""
    linear_dir = Path("src") / "smorg" / "integrations" / "linear"
    files = [linear_dir / "panel.py", linear_dir / "glyphs.py"] + sorted(
        linear_dir.glob("views/*.py")
    )
    for file in files:
        source = file.read_text()
        assert "httpx" not in source, file
        assert "McpSession" not in source, file
        assert "fetch" not in source, file


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

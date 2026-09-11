from dataclasses import replace

import pytest

from smorg.integrations.linear.panel import LinearPanel
from smorg.integrations.linear.source import Project
from smorg.integrations.linear.views import LinearView
from smorg.integrations.linear.views.project import LinearProjectView
from smorg.integrations.linear.views.project_issues import LinearProjectIssues

from .helpers import PanelHarness, panel_with, project, project_detail, viewer


def view_showing(shown=None, error: str | None = None, narrow: bool = False) -> LinearProjectView:
    panel = panel_with(viewer(), project("Redis"))
    panel.trail.push(project("Redis"))
    key = LinearPanel.detail_key(project("Redis"))
    if shown is not None:
        panel.show_detail(key, shown)
    if error is not None:
        panel.show_detail_error(key, error)
    view = LinearProjectView(panel)
    view.narrow = narrow
    return view


def rendered(view: LinearProjectView) -> str:
    return "\n".join(view.content_lines())


def _properties_of(item: Project) -> str:
    panel = panel_with(viewer(), item)
    panel.trail.push(item)
    view = LinearProjectView(panel)
    return rendered(view)


def test_the_issues_card_summarizes_the_counts_and_points_at_the_issues_view():
    text = rendered(view_showing(project_detail()))
    assert "1 in progress · 1 in review · 1 todo · 2 backlog · 2 done" in text
    assert "⏎ to open" in text
    assert "title of A" not in text


def test_the_dates_row_names_a_lone_start_or_a_lone_target():
    dated = project("Redis", target_date="2027-01-31", target_resolution="halfYear")
    assert "Aug 4 → H1 2027" in _properties_of(dated)
    start_only = project("Redis")
    assert "from Aug 4" in _properties_of(start_only)
    target_only = replace(dated, start_date="")
    assert "due H1 2027" in _properties_of(target_only)


def test_before_the_detail_lands_the_page_shows_the_project_alone():
    text = rendered(view_showing())
    assert "Redis" in text and "loading…" in text
    assert "could not load: boom" in rendered(view_showing(error="boom"))


def test_the_sidebar_folds_under_the_title_when_narrow():
    wide = rendered(view_showing(project_detail()))
    narrow = rendered(view_showing(project_detail(), narrow=True))
    assert "Properties" in wide
    assert "Properties" not in narrow and "In Progress" in narrow


@pytest.mark.asyncio
async def test_enter_opens_the_issues_view_and_back_returns_through_it():
    panel = panel_with(viewer(), project("Redis"))
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        panel.open_project(project("Redis"))
        panel.show_detail(LinearPanel.detail_key(project("Redis")), project_detail())
        await pilot.pause()
        assert panel.active_view is LinearView.PROJECT
        await pilot.press("enter")
        await pilot.pause()
        assert panel.active_view is LinearView.PROJECT_ISSUES
        panel.query_one(LinearProjectIssues).cursor = 1
        await pilot.press("enter")
        await pilot.pause()
        assert panel.active_view is LinearView.ISSUE
        assert panel.viewed is not None and panel.viewed.id == "C"
        await pilot.press("escape")
        await pilot.pause()
        assert panel.active_view is LinearView.PROJECT_ISSUES
        assert panel.query_one(LinearProjectIssues).cursor == 1
        await pilot.press("escape")
        await pilot.pause()
        assert panel.active_view is LinearView.PROJECT
        assert panel.trail_labels() == ("Redis",)
        await pilot.press("escape")
        await pilot.pause()
        assert panel.active_view is LinearView.PROJECTS

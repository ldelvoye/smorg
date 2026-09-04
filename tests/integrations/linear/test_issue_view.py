"""Tests for the issue view: rendering only, no network and no app unless a size matters."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from textual.containers import VerticalScroll

from smorg.core.contract import Newest
from smorg.integrations.linear.panel import LinearPanel
from smorg.integrations.linear.source import (
    Comment,
    Link,
    ParentSummary,
    RelatedIssue,
    SubIssue,
    Transition,
)
from smorg.integrations.linear.views.issue import (
    ACTIVITY_LIMIT,
    LinearIssueView,
    _format_due,
    _format_related_row,
    _format_sub_issue_row,
)
from smorg.shell.terminal_palette import StatusColors

from .helpers import NOW, PanelHarness, detail, issue, panel_with


def view_showing(shown=None, error: str | None = None, narrow: bool = False) -> LinearIssueView:
    panel = panel_with(issue("ENG-1"))
    panel.viewed = issue("ENG-1")
    key = LinearPanel.detail_key(panel.viewed)
    if shown is not None:
        panel.show_detail(key, shown)
    if error is not None:
        panel.show_detail_error(key, error)
    view = LinearIssueView(panel)
    view.narrow = narrow
    return view


def rendered(view: LinearIssueView) -> str:
    return "\n".join(view.content_lines())


def test_the_view_says_how_to_get_back():
    assert "‹ esc — issues" in rendered(view_showing(detail()))


def test_the_header_names_the_issue_before_detail_arrives():
    text = rendered(view_showing())
    assert "ENG-1 · Infra" in text
    assert "title of ENG-1" in text
    assert "loading…" in text


def test_the_header_carries_the_parent_line_only_with_a_parent():
    without = rendered(view_showing(detail()))
    assert "Sub-issue of" not in without

    parent = ParentSummary(
        id="ENG-0", title="the epic", status="In Progress", status_type="started"
    )
    with_parent = rendered(view_showing(detail(parent=parent)))
    assert "Sub-issue of ◐ ENG-0 the epic" in with_parent


def test_a_bare_issue_renders_only_status_priority_and_assignee_in_the_sidebar():
    text = rendered(view_showing(detail()))
    assert "Properties" in text
    assert "◕ In Review" in text
    assert "▂▄▆ High" in text
    assert "@ Lucas Delvoye" in text
    for absent in ("Labels", "Project", "Related", "Links", "sub-issues", "◭", "◷"):
        assert absent not in text, absent


def test_every_section_renders_when_its_data_exists():
    full = detail(
        labels=("Tech Debt", "maintenance"),
        project="Improve Redis Scalability",
        milestone="Reduce forever data",
        due_date="2026-09-30",
        estimate="3",
        blocked_by=(RelatedIssue(id="ENG-5", title="Land the prerequisite"),),
        blocks=(RelatedIssue(id="ENG-7", title="Ship the thing"),),
        related=(RelatedIssue(id="ENG-10", title="r1"),),
        links=(Link(title="chore: widen", url="https://github.com/x/y/pull/12"),),
    )
    text = rendered(view_showing(full))
    assert "◭ 3" in text
    assert "◷ Sep 30" in text
    assert "● Tech Debt" in text and "● maintenance" in text
    assert "▣ Improve Redis Scalability" in text
    assert "└ ◇ Reduce forever data" in text
    assert "⊘ ENG-5 Land the prerequisite" in text
    assert "blocks ◌ ENG-7 Ship the thing" in text
    assert "◌ ENG-10 r1" in text
    assert "↗ chore: widen" in text
    assert text.index("Properties") < text.index("Labels") < text.index("Project")
    assert text.index("Project") < text.index("Related") < text.index("Links")


def test_a_related_row_links_its_id_to_the_issue_when_it_has_a_url():
    linked = RelatedIssue(id="ENG-10", title="r1", url="https://linear.app/x/issue/ENG-10")
    row = _format_related_row(linked, "◌", "dim", "")
    link_spans = [span for span in row.spans if "link " in str(span.style)]
    assert len(link_spans) == 1
    linked_text = row.plain[link_spans[0].start : link_spans[0].end]
    assert linked_text == "ENG-10"
    assert str(link_spans[0].style) == "dim link https://linear.app/x/issue/ENG-10"

    unlinked = RelatedIssue(id="ENG-11", title="r2")
    row = _format_related_row(unlinked, "◌", "dim", "")
    assert not [span for span in row.spans if "link " in str(span.style)]


def test_a_sub_issue_row_links_its_id_to_the_issue_when_it_has_a_url():
    colors = StatusColors(red="#f85149", yellow="#d29922", green="#3fb950")
    child = SubIssue(
        id="ENG-2",
        title="first child",
        status="Todo",
        status_type="unstarted",
        priority="",
        url="https://linear.app/x/issue/ENG-2",
    )
    row = _format_sub_issue_row(child, colors)
    link_spans = [span for span in row.spans if "link " in str(span.style)]
    assert len(link_spans) == 1
    assert row.plain[link_spans[0].start : link_spans[0].end] == "ENG-2"


def test_the_description_card_shows_markdown_or_a_placeholder():
    assert "the description" in rendered(view_showing(detail()))
    assert "no description" in rendered(view_showing(detail(description="")))


def test_the_sub_issues_card_counts_done_over_total_and_lists_children():
    children = (
        SubIssue(
            id="ENG-2",
            title="first child",
            status="Done",
            status_type="completed",
            priority="Medium",
        ),
        SubIssue(
            id="ENG-3", title="second child", status="Todo", status_type="unstarted", priority=""
        ),
    )
    text = rendered(view_showing(detail(sub_issues=children)))
    assert "sub-issues (1/2)" in text
    assert "● ENG-2  first child" in text
    assert "○ ENG-3  second child" in text


def test_due_dates_drop_the_year_only_inside_the_current_year(monkeypatch):
    monkeypatch.setattr(
        "smorg.integrations.linear.views.issue.now",
        lambda: datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert _format_due("2026-09-30") == "Sep 30"
    assert _format_due("2027-01-31") == "Jan 31, 2027"


def _transition(status: str, status_type: str, hours_ago: int) -> Transition:
    return Transition(status=status, status_type=status_type, at=NOW - timedelta(hours=hours_ago))


def _comment(body: str, hours_ago: int) -> Comment:
    return Comment(author="alice", body=body, created_at=NOW - timedelta(hours=hours_ago))


def test_activity_interleaves_transitions_and_comments_oldest_first(monkeypatch):
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW)
    shown = detail(
        creator="Alice Author",
        transitions=(
            _transition("Backlog", "backlog", 50),
            _transition("In Progress", "started", 10),
        ),
        comments=Newest(items=(_comment("first thoughts", 30), _comment("done", 5))),
    )
    text = rendered(view_showing(shown))
    assert "activity" in text
    order = [
        text.index("◌ created in Backlog by Alice Author · 2d"),
        text.index("first thoughts"),
        text.index("◐ moved to In Progress · 10h"),
        text.index("done"),
    ]
    assert order == sorted(order)


def test_activity_shows_only_the_newest_events_behind_a_hidden_count():
    transitions = tuple(
        _transition(f"S{index}", "started", 100 - index) for index in range(ACTIVITY_LIMIT + 3)
    )
    shown = detail(transitions=transitions, comments=Newest(items=(), hidden=2))
    text = rendered(view_showing(shown))
    assert "… 5 earlier events" in text
    assert "moved to S0" not in text
    assert f"moved to S{ACTIVITY_LIMIT + 2}" in text


def test_activity_is_omitted_when_there_is_nothing_to_show():
    assert "activity" not in rendered(view_showing(detail()))


def test_the_narrow_layout_folds_the_sidebar_into_the_header_and_trailing_cards():
    full = detail(
        labels=("Tech Debt",),
        project="Improve Redis Scalability",
        milestone="Reduce forever data",
        related=(RelatedIssue(id="ENG-10", title="r1"),),
        links=(Link(title="chore: widen", url="https://github.com/x/y/pull/12"),),
    )
    text = rendered(view_showing(full, narrow=True))
    assert "◕ In Review · ▂▄▆ High · @ Lucas Delvoye" in text
    assert "● Tech Debt" in text
    assert "▣ Improve Redis Scalability › ◇ Reduce forever data" in text
    assert "related (1)" in text
    assert "links (1)" in text
    assert "Properties" not in text
    assert text.index("description") < text.index("related (1)") < text.index("links (1)")


@pytest.mark.asyncio
async def test_the_sidebar_hides_below_the_breakpoint_and_returns_above_it(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    panel = panel_with(issue("ENG-1"))
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        panel.open_issue(issue("ENG-1"))
        await pilot.pause()
        sidebar = panel.query_one("#sidebar", VerticalScroll)
        assert sidebar.display is True

        await pilot.resize_terminal(80, 40)
        await pilot.pause()
        assert sidebar.display is False
        assert "◕ In Review · ▂▄▆ High" in "\n".join(
            panel.query_one(LinearIssueView).content_lines()
        )

        await pilot.resize_terminal(120, 40)
        await pilot.pause()
        assert sidebar.display is True


@pytest.mark.asyncio
async def test_a_hostile_description_and_title_never_reach_rich_markup(monkeypatch):
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)
    from textual.widgets import Static

    hostile = replace(issue("ENG-1"), title="[blue]Weird[/blue]")
    panel = panel_with(hostile)
    async with PanelHarness(panel).run_test(size=(120, 40)) as pilot:
        panel.open_issue(hostile)
        await pilot.pause()
        panel.show_detail(panel.detail_key(hostile), detail(description="[red]x[/red]"))
        await pilot.pause()
        body = panel.query_one("#reading-body", Static)
        rendered_lines = "".join(body.render_line(y).text for y in range(body.size.height))
    assert "[red]x[/red]" in rendered_lines
    assert "[blue]Weird[/blue]" in rendered_lines

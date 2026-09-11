"""The navigation decisions: what a page can open, the trail, and the breadcrumb."""

import pytest

from smorg.integrations.linear.navigation import (
    BREADCRUMB_CAP,
    UNKNOWN_UPDATED_AT,
    Target,
    Trail,
    format_project_row,
    format_trail,
    issue_of_target,
    targets_of,
)
from smorg.integrations.linear.source import Issue, ParentSummary, Project, RelatedIssue, SubIssue
from smorg.integrations.linear.views import LinearView
from smorg.shell.terminal_palette import StatusColors

from .helpers import detail, issue, project


def _target(identifier: str) -> Target:
    return Target(
        id=identifier,
        title=f"title of {identifier}",
        status="Todo",
        status_type="unstarted",
        priority="",
        url=f"https://linear.app/x/issue/{identifier}",
    )


def test_targets_come_in_linear_s_order_and_empty_sections_are_omitted():
    full = detail(
        parent=ParentSummary(id="ENG-0", title="epic", status="In Progress", status_type="started"),
        sub_issues=(
            SubIssue(id="ENG-2", title="a", status="Done", status_type="completed", priority=""),
            SubIssue(id="ENG-3", title="b", status="Todo", status_type="unstarted", priority=""),
        ),
        blocked_by=(RelatedIssue(id="ENG-5", title="c"),),
        blocks=(RelatedIssue(id="ENG-7", title="e"),),
        related=(RelatedIssue(id="ENG-9", title="d"),),
    )
    sections = targets_of(full)
    assert [heading for heading, _ in sections] == [
        "parent",
        "sub-issues (1/2)",
        "blocked by (1)",
        "blocks (1)",
        "related (1)",
    ]
    assert [target.id for _, targets in sections for target in targets] == [
        "ENG-0",
        "ENG-2",
        "ENG-3",
        "ENG-5",
        "ENG-7",
        "ENG-9",
    ]
    assert targets_of(detail()) == ()


def test_the_trail_pushes_duplicates_pops_one_and_pops_to_an_index():
    trail = Trail()
    trail.push(issue("ENG-1"))
    trail.push(issue("ENG-2"))
    trail.push(issue("ENG-1"))
    assert trail.depth() == 3
    assert [visit.item.id for visit in trail.visits] == ["ENG-1", "ENG-2", "ENG-1"]

    trail.remember(scroll_y=7, picker_cursor=2)
    assert (trail.visits[-1].scroll_y, trail.visits[-1].picker_cursor) == (7, 2)

    popped = trail.pop()
    assert popped is not None and popped.item.id == "ENG-1"
    assert trail.current() == issue("ENG-2")

    trail.pop_to(0)
    assert [visit.item.id for visit in trail.visits] == ["ENG-1"]
    trail.pop_to(-1)
    assert trail.visits == [] and trail.current() is None and trail.pop() is None


def test_the_trail_holds_projects_and_issues_alike_and_labels_each():
    trail = Trail()
    trail.push(project("Redis"))
    trail.push(issue("ENG-1"))
    assert isinstance(trail.current(), Issue)
    trail.pop()
    assert isinstance(trail.current(), Project)
    assert trail.root is LinearView.ISSUES


def test_a_project_row_is_its_disc_and_name():
    row = format_project_row(project("Redis"), StatusColors("r", "y", "g"), "#828fff", False)
    assert row.plain == "◐ Redis"


def test_a_target_in_the_list_resolves_to_that_item_and_a_foreign_one_to_a_synthetic_issue():
    listed = issue("ENG-2")
    resolved, is_item = issue_of_target(_target("ENG-2"), (listed,))
    assert resolved is listed and is_item is True

    synthetic, is_item = issue_of_target(_target("ENG-99"), (listed,))
    assert is_item is False
    assert synthetic.id == "ENG-99"
    assert synthetic.title == "title of ENG-99"
    assert synthetic.updated_at == UNKNOWN_UPDATED_AT
    assert (synthetic.team, synthetic.project) == ("", "")


FIVE_DEEP = ("INFRENG-415", "INFRENG-449", "INFRENG-570", "INFRENG-571", "INFRENG-572")


@pytest.mark.parametrize(
    ("budget", "expected"),
    [
        (80, "issues › INFRENG-415 › INFRENG-449 › INFRENG-570 › INFRENG-571 › INFRENG-572"),
        (72, "issues › … › INFRENG-449 › INFRENG-570 › INFRENG-571 › INFRENG-572 (5)"),
        (56, "issues › … › INFRENG-570 › INFRENG-571 › INFRENG-572 (5)"),
        (50, "… › INFRENG-570 › INFRENG-571 › INFRENG-572 (5)"),
        (44, "issues › … › INFRENG-571 › INFRENG-572 (5)"),
        (36, "… › INFRENG-571 › INFRENG-572 (5)"),
        (30, "issues › … › INFRENG-572 (5)"),
        (24, "… › INFRENG-572 (5)"),
        (16, "INFRENG-572 (5)"),
    ],
)
def test_the_breadcrumb_fits_its_budget_from_the_right(budget: int, expected: str) -> None:
    assert format_trail(FIVE_DEEP, budget).plain == expected


def test_the_breadcrumb_caps_the_shown_entries_on_a_wide_budget():
    nine_deep = tuple(f"ENG-{index}" for index in range(1, 10))
    rendered = format_trail(nine_deep, 200).plain
    assert rendered == "issues › … › ENG-5 › ENG-6 › ENG-7 › ENG-8 › ENG-9 (9)"
    assert rendered.count("ENG-") == BREADCRUMB_CAP


def test_the_breadcrumb_prefers_the_previous_entry_over_the_root():
    # 21 columns fit "… › ENG-1 › ENG-2 (2)" (21) but not "issues › ENG-1 › ENG-2" (22).
    rendered = format_trail(("ENG-1", "ENG-2"), 21).plain
    assert rendered == "… › ENG-1 › ENG-2 (2)"

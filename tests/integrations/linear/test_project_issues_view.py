from dataclasses import replace

from smorg.integrations.linear.panel import LinearPanel
from smorg.integrations.linear.views.project_issues import (
    LinearProjectIssues,
    TreeRow,
    _format_tree_row,
    issue_tree,
)
from smorg.shell.terminal_palette import StatusColors

from .helpers import ISSUES, panel_with, project, project_detail, project_issue, viewer


def view_showing(shown=None) -> LinearProjectIssues:
    panel = panel_with(viewer(), project("Redis"))
    panel.trail.push(project("Redis"))
    key = LinearPanel.detail_key(project("Redis"))
    if shown is not None:
        panel.show_detail(key, shown)
    return LinearProjectIssues(panel)


def rendered(view: LinearProjectIssues) -> str:
    return "\n".join(view.content_lines())


def _line_with(lines: list[str], needle: str) -> str:
    for line in lines:
        if needle in line:
            return line
    raise AssertionError(needle)


def test_the_tree_roots_in_flight_issues_and_hangs_their_whole_subtree_under_them():
    groups = issue_tree(ISSUES)
    names = [(status, [row.issue.id for row in rows]) for status, _, rows in groups]
    assert names == [("In Progress", ["A", "C", "D", "B"]), ("Todo", ["E"])]
    depths = {row.issue.id: row.depth for _, _, rows in groups for row in rows}
    assert depths == {"A": 0, "B": 1, "C": 1, "D": 2, "E": 0}


def test_custom_statuses_that_share_a_rank_still_group_together():
    roots = (
        project_issue("X", "Designing", "started"),
        project_issue("Y", "QA", "started"),
        project_issue("Z", "Designing", "started"),
    )
    groups = issue_tree(roots)
    names = [(status, [row.issue.id for row in rows]) for status, _, rows in groups]
    assert names == [("Designing", ["X", "Z"]), ("QA", ["Y"])]


def test_the_issues_card_opens_with_the_counts_and_marks_your_rows():
    text = rendered(view_showing(project_detail()))
    assert "1 in progress · 1 in review · 1 todo · 2 backlog · 2 done" in text
    assert "In Progress (1)" in text and "In Review (1)" not in text
    lines = text.splitlines()
    a_line = _line_with(lines, "title of A")
    a_cell = a_line.rstrip("│ ")
    assert a_cell.endswith("you")
    c_line = _line_with(lines, "title of C")
    c_cell = c_line.rstrip("│ ")
    assert c_cell.endswith("Scott")
    assert "├─" in _line_with(lines, "title of C") and "└─" in _line_with(lines, "title of B")
    assert "title of F" not in text and "title of G" not in text


def test_a_long_selected_tree_title_slides_and_the_assignee_column_stays_put():
    long_title = "an issue title that overflows the tree row by a wide margin " * 2
    long_issue = replace(project_issue("A", assignee="Scott Strong"), title=long_title)
    row = TreeRow(issue=long_issue, depth=0, prefix="├─ ")
    colors = StatusColors(red="#f85149", yellow="#d29922", green="#3fb950")
    still = _format_tree_row(row, True, "", colors, "#5e6ad2", 60, 0).plain
    slid = _format_tree_row(row, True, "", colors, "#5e6ad2", 60, 9).plain

    assert still != slid
    assert still.endswith("   Scott") and slid.endswith("   Scott")
    assert len(still) == len(slid)


def test_a_new_detail_replaces_the_cached_tree():
    view = view_showing(project_detail())
    key = LinearPanel.detail_key(project("Redis"))
    warmed = view._tree_rows()
    assert [row.issue.id for row in warmed] != ["Z"]

    other = project_detail(issues=(project_issue("Z", "Todo", "unstarted"),))
    view.panel.show_detail(key, other)
    rows = view._tree_rows()
    assert [row.issue.id for row in rows] == ["Z"]

    first = view._tree()
    view.panel.show_detail(key, other)
    second = view._tree()
    assert second is first


def test_triage_issues_count_on_the_counts_line_but_never_root_the_tree():
    detail = project_detail(
        issues=(
            project_issue("A", "In Progress", "started"),
            project_issue("B", "Triage", "triage"),
        )
    )
    text = rendered(view_showing(detail))
    assert "1 triage" in text
    groups = issue_tree(detail.issues)
    roots = [row for _, _, rows in groups for row in rows if row.depth == 0]
    assert len(roots) == 1

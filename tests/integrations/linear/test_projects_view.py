from smorg.integrations.linear.views.projects import LinearProjects

from .helpers import milestone, project, projects_with


def _lines(view: LinearProjects) -> list[str]:
    return view.content_lines()


def _line_with(lines: list[str], needle: str) -> str:
    for line in lines:
        if needle in line:
            return line
    raise AssertionError(needle)


def test_projects_group_by_status_started_first_then_priority_then_name():
    view = projects_with(
        project("Zeta", status="Planned", status_type="planned", priority="High"),
        project("Beta", priority="Low"),
        project("Alpha", priority="Low"),
        project("Gamma", priority="Urgent"),
    )
    text = "\n".join(_lines(view))
    assert text.index("In Progress (3)") < text.index("Planned (1)")
    assert text.index("Gamma") < text.index("Alpha") < text.index("Beta") < text.index("Zeta")
    first = view.selected_item()
    assert first is not None and first.name == "Gamma"
    view.cursor = 3
    last = view.selected_item()
    assert last is not None and last.name == "Zeta"


def test_a_project_row_carries_its_lead_and_target_and_each_milestone_its_bar():
    view = projects_with(
        project(
            "Redis",
            lead="Mark Story",
            target_date="2027-01-31",
            target_resolution="halfYear",
            milestones=(
                milestone("Reduce forever data", 52, "2026-10-31"),
                milestone("Move off", 0),
            ),
        ),
        project("Sudo"),
    )
    lines = _lines(view)
    redis = _line_with(lines, "Redis")
    assert "Mark Story · H1 2027" in redis
    bar_line = _line_with(lines, "Reduce forever data")
    assert "▰▰▰▰▰▱▱▱▱▱" in bar_line and " 52%" in bar_line and "Oct 31" in bar_line
    assert any("no milestones" in line for line in lines)


def test_no_projects_reads_as_one_dim_line():
    assert "no projects" in "\n".join(_lines(projects_with()))


def test_custom_statuses_that_share_a_rank_still_group_together():
    view = projects_with(
        project("X", status="Designing", status_type="planned", priority="High"),
        project("Y", status="Scoping", status_type="planned", priority="Medium"),
        project("Z", status="Designing", status_type="planned", priority="Low"),
    )
    text = "\n".join(_lines(view))
    assert text.count("Designing (2)") == 1
    assert text.count("Scoping (1)") == 1

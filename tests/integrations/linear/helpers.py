"""Shared fixtures for Linear panel/view tests."""

from __future__ import annotations

from datetime import UTC, datetime

from textual.app import App, ComposeResult

from smorg.core.contract import Item, Newest
from smorg.core.state import SeenState
from smorg.integrations.linear.panel import LinearPanel
from smorg.integrations.linear.source import (
    VIEWER_ID,
    Issue,
    IssueDetail,
    Milestone,
    Project,
    ProjectDetail,
    ProjectIssue,
    Viewer,
)
from smorg.integrations.linear.views.issues import LinearIssues
from smorg.integrations.linear.views.menu import LinearMenu
from smorg.integrations.linear.views.projects import LinearProjects
from smorg.shell.panel import PanelState

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def issue(identifier: str = "ENG-1", status: str = "In Review") -> Issue:
    return Issue(
        id=identifier,
        updated_at=NOW,
        url=f"https://linear.app/x/issue/{identifier}",
        title=f"title of {identifier}",
        status=status,
        status_type="started",
        team="Infra",
        priority="High",
        project="",
    )


def milestone(name: str = "Widen columns", progress: int = 0, target_date: str = "") -> Milestone:
    return Milestone(name=name, target_date=target_date, progress=progress)


def project(
    name: str = "Redis",
    status: str = "In Progress",
    status_type: str = "started",
    priority: str = "High",
    lead: str = "",
    target_date: str = "",
    target_resolution: str = "",
    milestones: tuple[Milestone, ...] = (),
) -> Project:
    slug = name.casefold().replace(" ", "-")
    return Project(
        id=f"project-{slug}",
        updated_at=NOW,
        url=f"https://linear.app/x/project/{slug}",
        name=name,
        summary="",
        status=status,
        status_type=status_type,
        priority=priority,
        lead=lead,
        teams=("INFRENG",),
        start_date="2026-08-04",
        target_date=target_date,
        target_resolution=target_resolution,
        milestones=milestones,
    )


def project_issue(
    identifier: str,
    status: str = "In Progress",
    status_type: str = "started",
    parent_id: str = "",
    assignee: str = "",
) -> ProjectIssue:
    return ProjectIssue(
        id=identifier,
        title=f"title of {identifier}",
        status=status,
        status_type=status_type,
        priority="Medium",
        url=f"https://linear.app/x/issue/{identifier}",
        assignee=assignee,
        parent_id=parent_id,
    )


ISSUES = (
    project_issue("A", assignee="Lucas Delvoye"),
    project_issue("B", "Backlog", "backlog", parent_id="A"),
    project_issue("C", "In Review", "started", parent_id="A", assignee="Scott Strong"),
    project_issue("D", "Done", "completed", parent_id="C"),
    project_issue("E", "Todo", "unstarted"),
    project_issue("F", "Backlog", "backlog"),
    project_issue("G", "Done", "completed"),
)


def project_detail(**overrides) -> ProjectDetail:
    fields = {
        "description": "Goal\n\nRedis is the last shared component.",
        "initiatives": ("It is reliable",),
        "milestones": (milestone("Reduce forever data", 52, "2026-10-31"),),
        "issues": ISSUES,
    }
    return ProjectDetail(**(fields | overrides))


def viewer(name: str = "Lucas Delvoye", handle: str = "lucas") -> Viewer:
    return Viewer(
        id=VIEWER_ID,
        updated_at=datetime(1970, 1, 1, tzinfo=UTC),
        url="https://linear.app",
        name=name,
        handle=handle,
    )


def detail(**overrides) -> IssueDetail:
    fields = {
        "description": "the description",
        "status": "In Review",
        "status_type": "started",
        "priority": "High",
        "team": "Infra",
        "assignee": "Lucas Delvoye",
        "creator": "",
        "labels": (),
        "project": "",
        "milestone": "",
        "due_date": "",
        "estimate": "",
        "parent": None,
        "sub_issues": (),
        "blocked_by": (),
        "blocks": (),
        "related": (),
        "links": (),
        "transitions": (),
        "comments": Newest(items=()),
    }
    return IssueDetail(**(fields | overrides))


def panel_with(*items: Item, seen: SeenState | None = None) -> LinearPanel:
    panel = LinearPanel()
    panel.state = PanelState.READY
    panel.items = items
    if seen is None:
        panel.seen = SeenState({})
    else:
        panel.seen = seen
    panel.integration_id = "linear"
    return panel


def issues_with(*issues: Issue, seen: SeenState | None = None) -> LinearIssues:
    return LinearIssues(panel_with(*issues, seen=seen))


def menu_with(*issues: Issue, seen: SeenState | None = None) -> LinearMenu:
    panel = panel_with(viewer(), *issues, seen=seen)
    return LinearMenu(panel)


def projects_with(*projects: Project, seen: SeenState | None = None) -> LinearProjects:
    panel = panel_with(viewer(), *projects, seen=seen)
    return LinearProjects(panel)


class PanelHarness(App[None]):
    """The smallest app that can mount a `LinearPanel` and hand it focus."""

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel

    def on_mount(self) -> None:
        self._panel.focus()

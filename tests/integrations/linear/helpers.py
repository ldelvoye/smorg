"""Shared fixtures for Linear panel/view tests."""

from __future__ import annotations

from datetime import UTC, datetime

from textual.app import App, ComposeResult

from smorg.core.contract import Item, Newest
from smorg.core.state import SeenState
from smorg.integrations.linear.panel import LinearPanel
from smorg.integrations.linear.source import VIEWER_ID, Issue, IssueDetail, Viewer
from smorg.integrations.linear.views.issues import LinearIssues
from smorg.integrations.linear.views.menu import LinearMenu
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


class PanelHarness(App[None]):
    """The smallest app that can mount a `LinearPanel` and hand it focus."""

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel

    def on_mount(self) -> None:
        self._panel.focus()

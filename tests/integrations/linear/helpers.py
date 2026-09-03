"""Shared fixtures for Linear panel/view tests."""

from __future__ import annotations

from datetime import UTC, datetime

from textual.app import App, ComposeResult

from smorg.core.contract import Newest
from smorg.core.state import SeenState
from smorg.integrations.linear.panel import LinearPanel
from smorg.integrations.linear.source import Issue, IssueDetail
from smorg.integrations.linear.views.issues import LinearIssues
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


def detail(**overrides) -> IssueDetail:
    fields = {
        "description": "the description",
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


def panel_with(*issues: Issue, seen: SeenState | None = None) -> LinearPanel:
    panel = LinearPanel()
    panel.state = PanelState.READY
    panel.items = issues
    panel.seen = seen or SeenState({})
    panel.integration_id = "linear"
    return panel


def issues_with(*issues: Issue, seen: SeenState | None = None) -> LinearIssues:
    return LinearIssues(panel_with(*issues, seen=seen))


class PanelHarness(App[None]):
    """The smallest app that can mount a `LinearPanel` and hand it focus."""

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel

    def on_mount(self) -> None:
        self._panel.focus()

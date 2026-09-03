"""Linear's tab: a host panel that swaps between the issue list and one issue's page."""

from __future__ import annotations

from collections.abc import Iterable

from textual.app import ComposeResult

from smorg.integrations.linear.source import Issue
from smorg.integrations.linear.views import LinearView
from smorg.integrations.linear.views.issue import LinearIssueView
from smorg.integrations.linear.views.issues import LinearIssues
from smorg.shell.panel import Panel


class LinearPanel(Panel):
    can_focus = False

    DEFAULT_CSS = """
    LinearPanel { align-horizontal: center; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.active_view = LinearView.ISSUES
        self.viewed: Issue | None = None

    def compose(self) -> ComposeResult:
        yield LinearIssues(self)
        yield LinearIssueView(self)

    def on_mount(self) -> None:
        self._sync_view_display()

    def show_view(self, view: LinearView) -> None:
        self.active_view = view
        self._sync_view_display()
        self._active_view_widget().focus()
        self.refresh()

    def open_issue(self, issue: Issue) -> None:
        """Show one issue full screen; its detail loads while the header renders."""
        self.viewed = issue
        if self.detail_error_for(issue) is not None:
            self.reload_detail(issue)
        else:
            self.request_detail(issue)
        self.mark_seen(issue)
        self.show_view(LinearView.ISSUE)

    def close_issue(self) -> None:
        self.viewed = None
        self.show_view(LinearView.ISSUES)

    def focus(self, scroll_visible: bool = True):
        self._active_view_widget().focus(scroll_visible)
        return self

    def _active_view_widget(self) -> LinearIssues | LinearIssueView:
        if self.active_view is LinearView.ISSUE:
            return self._issue_view()
        return self._issues()

    def _sync_view_display(self) -> None:
        showing_issue = self.active_view is LinearView.ISSUE
        self._issues().display = not showing_issue
        self._issue_view().display = showing_issue

    def _issues(self) -> LinearIssues:
        return self.query_one(LinearIssues)

    def _issue_view(self) -> LinearIssueView:
        return self.query_one(LinearIssueView)

    def refresh(
        self, *regions, repaint: bool = True, layout: bool = False, recompose: bool = False
    ):
        if self.is_mounted:
            self._sync_view_display()
            self._issue_view().refresh_content()
        return super().refresh(*regions, repaint=repaint, layout=layout, recompose=recompose)

    def help_bindings(self) -> Iterable[object]:
        if self.active_view is LinearView.ISSUE:
            return LinearIssueView.BINDINGS
        return LinearIssues.BINDINGS

    def issues(self) -> tuple[Issue, ...]:
        issues = [item for item in self.items if isinstance(item, Issue)]
        return tuple(issues)

    def selected_item(self) -> Issue | None:
        if self.active_view is LinearView.ISSUE:
            return self.viewed
        if not self.is_mounted:
            return None
        return self._issues().selected_item()

    def detail_keys_in_use(self) -> set[tuple[str, str]]:
        """The open issue's cache key survives pruning while it is on screen."""
        keys = super().detail_keys_in_use()
        if self.viewed is not None:
            keys.add(self.detail_key(self.viewed))
        return keys

    def ready_text(self) -> str:
        if not self.is_mounted:
            return super().ready_text()
        if self.active_view is LinearView.ISSUE:
            return "\n".join(self._issue_view().content_lines())
        return "\n".join(self._issues().content_lines())

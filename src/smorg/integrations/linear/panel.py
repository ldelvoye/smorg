"""Linear's tab: a host panel that swaps between the issue list and one issue's page."""

from __future__ import annotations

from collections.abc import Iterable

from textual.app import ComposeResult

from smorg.integrations.linear.navigation import Target, Trail, issue_of_target
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
        self.trail = Trail()

    @property
    def viewed(self) -> Issue | None:
        return self.trail.current()

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

    def open_issue(self, issue: Issue, mark: bool = True) -> None:
        """Show one issue full screen on top of the trail; its detail loads while the header
        renders.
        """
        self.remember_view_state()
        self.trail.push(issue)
        if self.detail_error_for(issue) is not None:
            self.reload_detail(issue)
        else:
            self.request_detail(issue)
        if mark:
            self.mark_seen(issue)
        self.show_view(LinearView.ISSUE)
        self._issue_view().restore_view_state(self.trail.visits[-1])

    def open_target(self, target: Target) -> None:
        issue, is_item = issue_of_target(target, self.issues())
        self.open_issue(issue, mark=is_item)

    def go_back(self) -> None:
        self.trail.pop()
        self._show_trail_top()

    def go_back_to(self, index: int) -> None:
        self.trail.pop_to(index)
        self._show_trail_top()

    def _show_trail_top(self) -> None:
        current = self.trail.current()
        if current is None:
            self.show_view(LinearView.ISSUES)
            return
        self.show_view(LinearView.ISSUE)
        self._issue_view().restore_view_state(self.trail.visits[-1])

    def remember_view_state(self) -> None:
        """Store the open page's scroll and picker cursor on its visit before leaving it."""
        if self.trail.current() is None or not self.is_mounted:
            return
        view = self._issue_view()
        self.trail.remember(view.reading_scroll_y(), view.picker_cursor)

    def trail_ids(self) -> tuple[str, ...]:
        ids = [visit.issue.id for visit in self.trail.visits]
        return tuple(ids)

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
        """Every page on the trail keeps its cache key while it can be returned to."""
        keys = super().detail_keys_in_use()
        for visit in self.trail.visits:
            keys.add(self.detail_key(visit.issue))
        return keys

    def ready_text(self) -> str:
        if not self.is_mounted:
            return super().ready_text()
        if self.active_view is LinearView.ISSUE:
            return "\n".join(self._issue_view().content_lines())
        return "\n".join(self._issues().content_lines())

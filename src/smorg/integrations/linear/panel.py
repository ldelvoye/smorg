"""Linear's tab: a host panel that swaps between the issue list and one issue's page."""

from __future__ import annotations

from textual.app import ComposeResult

from smorg.integrations.linear.navigation import Target, Trail, issue_of_target
from smorg.integrations.linear.palette import Glow, accent_for_background, glow_for_background
from smorg.integrations.linear.source import Issue, Viewer, _issue_url_base
from smorg.integrations.linear.views import LinearView
from smorg.integrations.linear.views.issue import LinearIssueView
from smorg.integrations.linear.views.issues import LinearIssues
from smorg.integrations.linear.views.menu import LinearMenu
from smorg.shell.view_host import HostedView, ViewHostPanel

_LINEAR_HOME = "https://linear.app"

_VIEW_CLASSES: dict[LinearView, type[HostedView]] = {
    LinearView.MENU: LinearMenu,
    LinearView.ISSUES: LinearIssues,
    LinearView.ISSUE: LinearIssueView,
}


class LinearPanel(ViewHostPanel[LinearView]):
    DEFAULT_CSS = """
    LinearPanel { align-horizontal: center; }
    """

    def __init__(self) -> None:
        super().__init__(LinearView.MENU)
        self.trail = Trail()

    def view_classes(self) -> dict[LinearView, type[HostedView]]:
        return _VIEW_CLASSES

    def accent(self) -> str:
        """Linear's brand indigo, picked to sit on this terminal's background."""
        return accent_for_background(self._terminal_background())

    def glow(self) -> Glow:
        return glow_for_background(self._terminal_background())

    @property
    def viewed(self) -> Issue | None:
        return self.trail.current()

    def compose(self) -> ComposeResult:
        yield LinearMenu(self)
        yield LinearIssues(self)
        yield LinearIssueView(self)

    def fetch_started(self) -> None:
        if not self.is_mounted:
            return
        self._menu().fetch_started()

    def fetch_finished(self) -> None:
        if not self.is_mounted:
            return
        self._menu().fetch_finished()

    def show_view(self, view: LinearView) -> None:
        super().show_view(view)
        if view is not LinearView.ISSUES or not self.is_mounted:
            return
        self._menu().acknowledge_changes()

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

    def _issues(self) -> LinearIssues:
        return self.query_one(LinearIssues)

    def _issue_view(self) -> LinearIssueView:
        return self.query_one(LinearIssueView)

    def _menu(self) -> LinearMenu:
        return self.query_one(LinearMenu)

    def issues(self) -> tuple[Issue, ...]:
        issues = [item for item in self.items if isinstance(item, Issue)]
        return tuple(issues)

    def viewer(self) -> Viewer | None:
        for item in self.items:
            if isinstance(item, Viewer):
                return item
        return None

    def home_url(self) -> str:
        issues = self.issues()
        if not issues:
            return _LINEAR_HOME
        url_base = _issue_url_base(issues[0].url)
        if not url_base:
            return _LINEAR_HOME
        return url_base.removesuffix("issue/")

    def mark_all_seen(self) -> None:
        self.seen.mark_all_seen(self.integration_id, self.issues())
        self._save_seen()
        self.refresh()

    def selected_item(self) -> Issue | None:
        if self.active_view is LinearView.MENU:
            return None
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

"""GitHub's tab: a host panel that swaps between full views owned by this integration."""

from __future__ import annotations

from collections.abc import Iterable

from rich.console import RenderableType
from textual.app import ComposeResult

from smorg.core.contract import Item
from smorg.integrations.github.source import PullRequest
from smorg.integrations.github.views.inbox import GitHubInbox
from smorg.shell.panel import Panel


class GitHubPanel(Panel):
    # A focusable host with no bindings of its own would be a dead stop in the tab-key focus
    # chain — Textual bindings bubble up from the focused node, never down to it. Left False so
    # focus_next/previous skip straight to the inbox; a later task makes it focusable only during
    # a loading takeover.
    can_focus = False

    def compose(self) -> ComposeResult:
        yield GitHubInbox(self)

    def focus(self, scroll_visible: bool = True):
        self._inbox().focus(scroll_visible)
        return self

    def _inbox(self) -> GitHubInbox:
        return self.query_one(GitHubInbox)

    def help_bindings(self) -> Iterable[object]:
        return GitHubInbox.BINDINGS

    def pull_requests(self) -> tuple[PullRequest, ...]:
        prs = [item for item in self.items if isinstance(item, PullRequest)]
        return tuple(prs)

    def mark_all_seen(self) -> None:
        """Mark every shown pull request seen; other item kinds never enter the store."""
        self.seen.mark_all_seen(self.integration_id, self.pull_requests())
        self._save_seen()
        self.refresh()

    def selected_item(self) -> PullRequest | None:
        if not self.is_mounted:
            return None
        return self._inbox().selected_item()

    def render_detail(self, item: Item, detail: object) -> RenderableType:
        if not self.is_mounted:
            return super().render_detail(item, detail)
        return self._inbox().render_detail(item, detail)

    def ready_text(self) -> str:
        if not self.is_mounted:
            return super().ready_text()
        return "\n".join(self._inbox().content_lines())

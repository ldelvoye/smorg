"""The pushed-branches view: recently pushed branches with no pull request yet, one card."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from smorg.integrations.github.source import PushedBranch
from smorg.integrations.github.views import GitHubView
from smorg.shell.cards import format_card, format_card_title, format_marked_cell
from smorg.shell.cursor import clamp_cursor, step_cursor
from smorg.shell.format import age, plain_lines
from smorg.shell.panel import PanelState, ViewBody
from smorg.shell.terminal_palette import StatusColors
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.github.panel import GitHubPanel

_BACK_HINT = "‹ esc — menu"
_UNAVAILABLE_TEXT = "pushed branches unavailable with this token"
_EMPTY_TEXT = "nothing recently pushed"
_FINE_GRAINED_HINT = "a fine-grained token may need contents read access"


def _format_meta(branch: PushedBranch) -> str:
    """ "octocat/hello · fix the loader race · 3h"."""
    when = age(branch.updated_at)
    return f"{branch.repository} · {branch.headline} · {when}"


def _format_failed_count(count: int) -> str:
    """ "3 repos couldn't be checked this refresh"."""
    if count == 1:
        noun = "repo"
    else:
        noun = "repos"
    return f"{count} {noun} couldn't be checked this refresh"


class GitHubPushedBranches(Vertical, HostedView):
    BINDINGS = [
        Binding("up", "cursor_up", "select branch", show=False),
        Binding("down", "cursor_down", "select branch", show=False),
        Binding("o", "open_selected", "open a create-PR page on GitHub", show=False),
        Binding("escape", "back_to_menu", "back to menu", show=False),
    ]
    can_focus = True

    DEFAULT_CSS = """
    GitHubPushedBranches { align-horizontal: center; }
    /* The cap keeps repository · headline · age near the names on wide terminals; the
     * centering places the capped body like the menu's composition. */
    GitHubPushedBranches > #pushed-body { height: 1fr; max-width: 120; }
    """

    def __init__(self, panel: GitHubPanel) -> None:
        super().__init__()
        self.panel = panel
        self.cursor = 0

    def compose(self) -> ComposeResult:
        yield ViewBody(self._render_body, id="pushed-body")

    def _render_body(self) -> RenderableType:
        if self.panel.state is PanelState.READY:
            return self.render_view()
        return self.panel.body_text()

    def _branches(self) -> tuple[PushedBranch, ...]:
        container = self.panel.pushed_branches()
        if container is None:
            return ()
        return container.branches

    def _selected_in(self, branches: tuple[PushedBranch, ...]) -> PushedBranch | None:
        if not branches:
            return None
        index = clamp_cursor(self.cursor, len(branches))
        return branches[index]

    def selected_branch(self) -> PushedBranch | None:
        return self._selected_in(self._branches())

    def render_view(self) -> RenderableType:
        """The whole ready view: the back hint above the card, and any check failures below."""
        parts = [
            Text(_BACK_HINT, style="dim"),
            Text(),
            self.render_content(),
        ]
        container = self.panel.pushed_branches()
        if container is not None and not container.unavailable and container.failed_repos:
            count_text = _format_failed_count(len(container.failed_repos))
            parts.append(Text())
            parts.append(Text(count_text, style="dim"))
            if container.fine_grained_token:
                parts.append(Text(_FINE_GRAINED_HINT, style="dim"))
        return Group(*parts)

    def render_content(self) -> RenderableType:
        container = self.panel.pushed_branches()
        if container is None or container.unavailable:
            return Text(_UNAVAILABLE_TEXT, style="dim")
        branches = container.branches
        if not branches:
            return Text(_EMPTY_TEXT, style="dim")
        selected = self._selected_in(branches)
        colors = self.panel.status_colors()
        lines: list[RenderableType] = []
        for branch in branches:
            if lines:
                lines.append(Text())
            head, meta = self._format_cell(branch, branch is selected, colors)
            lines.append(head)
            lines.append(meta)
        title = format_card_title(f"pushed branches ({len(branches)})")
        return format_card(title, lines)

    def content_lines(self) -> list[str]:
        """render_view flattened to plain text, so the two cannot drift apart."""
        return plain_lines(self.render_view())

    def _format_cell(
        self, branch: PushedBranch, selected: bool, colors: StatusColors
    ) -> tuple[Text, Text]:
        """A pushed branch's two lines: the marked name, then its dim repository · headline ·
        age.
        """
        changed = self.panel.seen.is_changed(self.panel.integration_id, branch)
        meta = _format_meta(branch)
        return format_marked_cell(branch.branch, meta, selected, changed, colors.green)

    def action_open_selected(self) -> None:
        branch = self.selected_branch()
        if branch is None:
            return
        webbrowser.open(branch.compare_url)
        self.panel.mark_seen(branch)

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def _move(self, offset: int) -> None:
        branches = self._branches()
        if not branches:
            return
        self.cursor = step_cursor(self.cursor, offset, len(branches))
        self.panel.refresh()

    def action_back_to_menu(self) -> None:
        self.panel.show_view(GitHubView.MENU)

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#pushed-body", Static).refresh()

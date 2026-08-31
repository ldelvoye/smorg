"""The pushed-branches view: recently pushed branches with no pull request yet, one card."""

from __future__ import annotations

import io
import webbrowser
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel as Card
from rich.text import Text
from textual.app import ComposeResult, RenderResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from smorg.integrations.github.source import PushedBranch
from smorg.integrations.github.views import CHANGED_MARK, SELECTED_MARK, GitHubView
from smorg.shell.format import age
from smorg.shell.panel import PanelState
from smorg.shell.terminal_palette import StatusColors

if TYPE_CHECKING:
    from smorg.integrations.github.panel import GitHubPanel

_BACK_HINT = "‹ esc — menu"
_UNAVAILABLE_TEXT = "pushed branches unavailable with this token"
_EMPTY_TEXT = "nothing recently pushed"
_FINE_GRAINED_HINT = "a fine-grained token may need contents read access"
_CARD_TITLE_STYLE = "bold not dim"


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


class _PushedBody(Static):
    """Draws the pushed-branches view's content; owns no state of its own."""

    def __init__(self, view: GitHubPushedBranches) -> None:
        # markup off: rows carry server-controlled text, so a hostile branch name can't style,
        # hide, or garble the view via Rich markup.
        # Not "body": the base Panel.refresh queries "#body", which the inbox already owns.
        super().__init__(markup=False, id="pushed-body")
        self._view = view

    def render(self) -> RenderResult:
        panel = self._view.panel
        if panel.state is PanelState.READY:
            return self._view.render_view()
        return panel.body_text()


class GitHubPushedBranches(Vertical):
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
        yield _PushedBody(self)

    def _branches(self) -> tuple[PushedBranch, ...]:
        container = self.panel.pushed_branches()
        if container is None:
            return ()
        return container.branches

    def _selected_in(self, branches: tuple[PushedBranch, ...]) -> PushedBranch | None:
        if not branches:
            return None
        index = min(self.cursor, len(branches) - 1)
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
        title = Text(f"pushed branches ({len(branches)})", style=_CARD_TITLE_STYLE)
        return Card(
            Group(*lines),
            title=title,
            title_align="left",
            box=box.ROUNDED,
            border_style="dim",
            padding=(0, 1),
        )

    def content_lines(self) -> list[str]:
        """render_view flattened to plain text, so the two cannot drift apart."""
        console = Console(width=80, file=io.StringIO(), force_terminal=False)
        with console.capture() as capture:
            console.print(self.render_view())
        return capture.get().splitlines()

    def _format_cell(
        self, branch: PushedBranch, selected: bool, colors: StatusColors
    ) -> tuple[Text, Text]:
        """A pushed branch's two lines: the marked name, then its dim repository · headline ·
        age.
        """
        head = Text()
        if selected:
            head.append(SELECTED_MARK, style="bold")
        else:
            head.append(" ")
        head.append(" ")
        changed = self.panel.seen.is_changed(self.panel.integration_id, branch)
        if changed:
            head.append(CHANGED_MARK, style=colors.green)
        else:
            head.append(" ")
        head.append(" ")
        if selected:
            head.append(branch.branch, style="bold")
        else:
            head.append(branch.branch)
        head.no_wrap = True
        head.overflow = "ellipsis"
        meta = Text()
        meta.append("    ")
        meta.append(_format_meta(branch), style="dim")
        meta.no_wrap = True
        meta.overflow = "ellipsis"
        return head, meta

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
        index = min(self.cursor, len(branches) - 1)
        self.cursor = (index + offset) % len(branches)
        self.panel.refresh()

    def action_back_to_menu(self) -> None:
        self.panel.show_view(GitHubView.MENU)

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        self.query_one(_PushedBody).refresh()

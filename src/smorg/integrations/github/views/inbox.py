"""The inbox view: every pull request as a two-line cell inside its category's card —

- "review inbox" for what other people are waiting on you for
- "your pull requests" for what you are waiting on other people for
"""

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

from smorg.integrations.github.source import Category, PullRequest
from smorg.integrations.github.views import CHANGED_MARK, SELECTED_MARK, GitHubView
from smorg.shell.format import age
from smorg.shell.panel import PanelState
from smorg.shell.terminal_palette import StatusColors

if TYPE_CHECKING:
    from smorg.integrations.github.panel import GitHubPanel

_EMPTY_BAND = "all caught up"
_BACK_HINT = "‹ esc — menu"

_BAND_TITLE_STYLE = "bold underline"


def _category_style(category: Category, colors: StatusColors) -> str:
    if category is Category.NEEDS_YOUR_REVIEW or category is Category.NEEDS_ACTION:
        return f"bold not dim {colors.red}"
    if category is Category.WAITING:
        return f"bold not dim {colors.yellow}"
    if category is Category.READY_TO_MERGE:
        return f"bold not dim {colors.green}"
    return "bold not dim"


_BANDS: tuple[tuple[str, tuple[Category, ...]], ...] = (
    (
        "review inbox",
        (Category.NEEDS_YOUR_REVIEW, Category.NEEDS_TEAM_REVIEW),
    ),
    (
        "your pull requests",
        (Category.DRAFT, Category.WAITING, Category.NEEDS_ACTION, Category.READY_TO_MERGE),
    ),
)

Section = tuple[Category, tuple[PullRequest, ...]]
Band = tuple[str, tuple[Section, ...]]


def _bands_of(pulls: tuple[PullRequest, ...]) -> tuple[Band, ...]:
    """Both bands with only their non-empty categories, in display order."""
    grouped: dict[Category, list[PullRequest]] = {}
    for pr in pulls:
        grouped.setdefault(pr.category, []).append(pr)
    bands: list[Band] = []
    for title, categories in _BANDS:
        sections: list[Section] = []
        for category in categories:
            prs = grouped.get(category, [])
            if prs:
                sections.append((category, tuple(prs)))
        bands.append((title, tuple(sections)))
    return tuple(bands)


def _ordered(bands: tuple[Band, ...]) -> tuple[PullRequest, ...]:
    """Every shown pull request as one sequence, in the order the bands draw them."""
    ordered: list[PullRequest] = []
    for _, sections in bands:
        for _, prs in sections:
            ordered.extend(prs)
    return tuple(ordered)


def _format_heading(category: Category, prs: tuple[PullRequest, ...]) -> str:
    """NEEDS_YOUR_REVIEW and three pull requests -> "needs your review (3)" """
    return f"{category} ({len(prs)})"


def _format_meta(pr: PullRequest) -> str:
    """ "octocat · 3h", or the age alone for a deleted account."""
    when = age(pr.updated_at)
    if not pr.author:
        return when
    return f"{pr.author} · {when}"


class _InboxBody(Static):
    """Draws the inbox's bands and state text; owns no state of its own."""

    def __init__(self, inbox: GitHubInbox) -> None:
        # markup off: rows carry server-controlled text, so a hostile title can't style,
        # hide, or garble the inbox via Rich markup.
        super().__init__(markup=False, id="body")
        self._inbox = inbox

    def render(self) -> RenderResult:
        panel = self._inbox.panel
        if panel.state is PanelState.READY:
            return self._inbox.render_view()
        return panel.body_text()


class GitHubInbox(Vertical):
    BINDINGS = [
        Binding("up", "cursor_up", "select pull request", show=False),
        Binding("down", "cursor_down", "select pull request", show=False),
        Binding("o", "open_selected", "open in GitHub", show=False),
        Binding("enter", "open_pull_request", "view pull request", show=False),
        Binding("escape", "back_to_menu", "back to menu", show=False),
    ]
    can_focus = True

    DEFAULT_CSS = """
    GitHubInbox { align-horizontal: center; }
    /* The cap keeps author · age near the titles on wide terminals; the centering
     * places the capped body like the menu's composition. */
    GitHubInbox > #body { height: 1fr; max-width: 120; }
    """

    def __init__(self, panel: GitHubPanel) -> None:
        super().__init__()
        self.panel = panel
        self.cursor = 0

    def compose(self) -> ComposeResult:
        yield _InboxBody(self)

    def _bands(self) -> tuple[Band, ...]:
        return _bands_of(self.panel.pull_requests())

    def _selected_in(self, bands: tuple[Band, ...]) -> PullRequest | None:
        ordered = _ordered(bands)
        if not ordered:
            return None
        index = min(self.cursor, len(ordered) - 1)
        return ordered[index]

    def selected_item(self) -> PullRequest | None:
        return self._selected_in(self._bands())

    def selected_url(self) -> str | None:
        pr = self.selected_item()
        if pr is None:
            return None
        return pr.url

    def render_view(self) -> RenderableType:
        """The whole ready view: the back hint above the bands."""
        return Group(Text(_BACK_HINT, style="dim"), Text(), self.render_content())

    def render_content(self) -> RenderableType:
        bands = self._bands()
        selected = self._selected_in(bands)
        colors = self.panel.status_colors()
        parts: list[RenderableType] = []
        for title, sections in bands:
            if parts:
                parts.append(Text())
            parts.append(Text(title, style=_BAND_TITLE_STYLE))
            parts.append(Text())
            if not sections:
                parts.append(Text(_EMPTY_BAND, style="dim"))
                continue
            for index, (category, prs) in enumerate(sections):
                if index > 0:
                    parts.append(Text())
                parts.append(self._format_section_card(category, prs, selected, colors))
        return Group(*parts)

    def content_lines(self) -> list[str]:
        """render_view flattened to plain text, so the two cannot drift apart."""
        console = Console(width=80, file=io.StringIO(), force_terminal=False)
        with console.capture() as capture:
            console.print(self.render_view())
        return capture.get().splitlines()

    def _format_section_card(
        self,
        category: Category,
        prs: tuple[PullRequest, ...],
        selected: PullRequest | None,
        colors: StatusColors,
    ) -> RenderableType:
        lines: list[RenderableType] = []
        for pr in prs:
            if lines:
                lines.append(Text())
            head, meta = self._format_cell(pr, pr is selected, colors)
            lines.append(head)
            lines.append(meta)
        heading = Text(_format_heading(category, prs), style=_category_style(category, colors))
        return Card(
            Group(*lines),
            title=heading,
            title_align="left",
            box=box.ROUNDED,
            border_style="dim",
            padding=(0, 1),
        )

    def _format_cell(
        self, pr: PullRequest, selected: bool, colors: StatusColors
    ) -> tuple[Text, Text]:
        """A pull request's two lines: the marked title, then its dim reference · author · age."""
        head = Text()
        if selected:
            head.append(SELECTED_MARK, style="bold")
        else:
            head.append(" ")
        head.append(" ")
        changed = self.panel.seen.is_changed(self.panel.integration_id, pr)
        if changed:
            head.append(CHANGED_MARK, style=colors.green)
        else:
            head.append(" ")
        head.append(" ")
        if selected:
            head.append(pr.title, style="bold")
        else:
            head.append(pr.title)
        head.no_wrap = True
        head.overflow = "ellipsis"
        meta = Text()
        meta.append("    ")
        meta.append(f"{pr.repository}#{pr.number} · {_format_meta(pr)}", style="dim")
        meta.no_wrap = True
        meta.overflow = "ellipsis"
        return head, meta

    def action_open_selected(self) -> None:
        pr = self.selected_item()
        if pr is None:
            return
        webbrowser.open(pr.url)
        self.panel.mark_seen(pr)

    def action_open_pull_request(self) -> None:
        pr = self.selected_item()
        if pr is None:
            return
        self.panel.open_pull_request(pr)

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def _move(self, offset: int) -> None:
        ordered = _ordered(self._bands())
        if not ordered:
            return
        index = min(self.cursor, len(ordered) - 1)
        self.cursor = (index + offset) % len(ordered)
        self.panel.refresh()

    def action_back_to_menu(self) -> None:
        self.panel.show_view(GitHubView.MENU)

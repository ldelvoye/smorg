"""The diff view: a two-column file list and patch reader, opened from the pull request."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.panel import Panel as Card
from rich.text import Text
from textual.app import ComposeResult, RenderResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.geometry import Region
from textual.widgets import Static

from smorg.integrations.github.loading import GitHubLoading
from smorg.integrations.github.source import (
    ABSENT_COUNT,
    DiffRequest,
    FileDiff,
    PullRequest,
    PullRequestDetail,
    PullRequestDiff,
)
from smorg.shell.cards import SELECTED_MARK, format_card, format_card_title, format_count
from smorg.shell.format import plain_lines
from smorg.shell.marquee import MARQUEE_STYLE, RowMarquee, marquee_overflow, marquee_window
from smorg.shell.panel import GutteredScroll
from smorg.shell.terminal_palette import StatusColors
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.github.panel import GitHubPanel

_BACK_HINT = "‹ esc — pull request"
# The row width tracks #diff-files-scroll in DEFAULT_CSS: its 48 cells minus its side
# padding (4) and the file-list card's border and padding (4).
_FILE_ROW_WIDTH = 40


def _format_files_count(diff: PullRequestDiff) -> str:
    if diff.truncated:
        return f"{len(diff.files)}+"
    return str(len(diff.files))


def _format_files_label(diff: PullRequestDiff) -> str:
    count = _format_files_count(diff)
    if count == "1":
        return "1 file"
    return f"{count} files"


def _format_volume_segment(diff: PullRequestDiff, detail: PullRequestDetail | None) -> Text:
    parts: list[str] = []
    if detail is not None and detail.counts.commits != ABSENT_COUNT:
        parts.append(format_count(detail.counts.commits, "commit"))
    parts.append(_format_files_label(diff))
    return Text(", ".join(parts), style="dim")


def _format_totals_line(
    diff: PullRequestDiff, detail: PullRequestDetail | None, colors: StatusColors
) -> Text:
    segments: list[Text] = []
    if detail is not None and detail.head and detail.base:
        segments.append(Text(f"{detail.base} ← {detail.head}", style="dim"))
    segments.append(_format_volume_segment(diff, detail))
    additions = sum(file.additions for file in diff.files if file.additions != ABSENT_COUNT)
    deletions = sum(file.deletions for file in diff.files if file.deletions != ABSENT_COUNT)
    change = Text()
    change.append(f"+{additions}", style=colors.green)
    change.append(" ")
    change.append(f"−{deletions}", style=colors.red)
    segments.append(change)
    line = Text()
    for index, segment in enumerate(segments):
        if index > 0:
            line.append(" · ", style="dim")
        line.append_text(segment)
    return line


def _format_header_lines(
    pr: PullRequest,
    diff: PullRequestDiff | None,
    detail: PullRequestDetail | None,
    colors: StatusColors,
) -> list[RenderableType]:
    reference = Text(f"{pr.repository}#{pr.number}", style="dim")
    title = Text(pr.title, style="bold")
    lines: list[RenderableType] = [reference, title]
    if diff is not None:
        lines.append(_format_totals_line(diff, detail, colors))
    return lines


def _format_file_counts(file: FileDiff) -> str:
    if file.additions == ABSENT_COUNT or file.deletions == ABSENT_COUNT:
        return ""
    return f"+{file.additions} −{file.deletions}"


def _row_path_width(counts: str) -> int:
    width = _FILE_ROW_WIDTH - 2
    if counts:
        width = width - len(counts) - 1
    return width


def _format_full_file_row(file: FileDiff, selected: bool) -> Text:
    counts = _format_file_counts(file)
    row = Text()
    if selected:
        row.append(SELECTED_MARK, style="bold")
        path_style = "bold"
    else:
        row.append(" ")
        path_style = ""
    row.append(" ")
    path_width = _row_path_width(counts)
    if selected:
        path_start = len(row.plain)
        row.append(file.path, style=path_style)
        row.stylize(MARQUEE_STYLE, path_start, path_start + len(file.path))
    elif len(file.path) <= path_width:
        row.append(file.path, style=path_style)
    else:
        head = file.path[: path_width - 1]
        row.append(f"{head}…", style=path_style)
    if counts:
        row.append(" ")
        row.append(counts, style="dim")
    return row


def _format_file_row(file: FileDiff, selected: bool, marquee_offset: int) -> Text:
    row = _format_full_file_row(file, selected)
    fitted = marquee_window(row, _FILE_ROW_WIDTH, marquee_offset)
    fitted.no_wrap = True
    fitted.overflow = "ellipsis"
    return fitted


def _format_file_title(file: FileDiff, colors: StatusColors) -> Text:
    if file.previous_path:
        name = f"{file.previous_path} → {file.path}"
    else:
        name = file.path
    title = format_card_title(name)
    if file.additions != ABSENT_COUNT and file.deletions != ABSENT_COUNT:
        title.append(" · ")
        title.append(f"+{file.additions}", style=colors.green)
        title.append(" ")
        title.append(f"−{file.deletions}", style=colors.red)
    return title


def _patch_line_style(line: str, colors: StatusColors) -> str | None:
    if line.startswith("+"):
        return colors.green
    if line.startswith("-"):
        return colors.red
    if line.startswith("@@"):
        return "dim"
    return None


def _format_patch_line(line: str, colors: StatusColors) -> Text:
    style = _patch_line_style(line, colors)
    if style is None:
        return Text(line, no_wrap=True, overflow="ellipsis")
    return Text(line, style=style, no_wrap=True, overflow="ellipsis")


def _format_card_body(patch: str, colors: StatusColors) -> list[RenderableType]:
    if not patch:
        return [Text("no textual diff", style="dim")]
    lines = patch.split("\n")
    return [_format_patch_line(line, colors) for line in lines]


def _format_file_card(file: FileDiff, colors: StatusColors) -> Card:
    title = _format_file_title(file, colors)
    body = _format_card_body(file.patch, colors)
    return format_card(title, body)


class _DiffHeader(Static):
    def __init__(self, view: GitHubDiffView) -> None:
        super().__init__(markup=False, id="diff-header")
        self._view = view

    def render(self) -> RenderResult:
        return self._view.render_header()


class _DiffFileList(Static):
    DEFAULT_CSS = """
    _DiffFileList { height: auto; }
    """

    def __init__(self, view: GitHubDiffView) -> None:
        super().__init__(markup=False, id="diff-files")
        self._view = view

    def render(self) -> RenderResult:
        return self._view.render_file_list()


class _DiffCard(Static):
    DEFAULT_CSS = """
    _DiffCard { height: auto; }
    """

    def __init__(self, view: GitHubDiffView) -> None:
        super().__init__(markup=False, id="diff-card")
        self._view = view

    def render(self) -> RenderResult:
        return self._view.render_card()


class GitHubDiffView(Vertical, HostedView):
    BINDINGS = [
        Binding("j", "next_file", "next file", show=False),
        Binding("k", "previous_file", "previous file", show=False),
        Binding("o", "open_in_github", "open in GitHub", show=False),
        Binding("escape", "back_to_pull_request", "back to pull request", show=False),
    ]
    can_focus = True

    DEFAULT_CSS = """
    GitHubDiffView { height: 1fr; }
    GitHubDiffView > #diff-header { height: auto; padding: 0 2; margin-bottom: 1; }
    GitHubDiffView > #diff-body { height: 1fr; }
    GitHubDiffView > #diff-body > #diff-files-scroll { width: 48; padding: 0 2; }
    GitHubDiffView > #diff-body > #diff-card-scroll { width: 1fr; }
    """

    def __init__(self, panel: GitHubPanel) -> None:
        super().__init__()
        self.panel = panel
        self.selected_index = 0
        self._shown_request: DiffRequest | None = None
        self.marquee = RowMarquee(self, self._selected_overflow, self._refresh_file_list)

    def compose(self) -> ComposeResult:
        yield _DiffHeader(self)
        with Horizontal(id="diff-body"):
            with GutteredScroll(id="diff-files-scroll"):
                yield _DiffFileList(self)
            with GutteredScroll(id="diff-card-scroll"):
                yield _DiffCard(self)
        yield GitHubLoading("loading the diff", id="diff-loading")

    def on_mount(self) -> None:
        self.refresh_content()

    def on_show(self) -> None:
        self.marquee.start()

    def on_hide(self) -> None:
        self.marquee.stop()

    def refresh_content(self) -> None:
        if not self.is_mounted:
            return
        request = self.panel.viewed_diff
        if request is None:
            loading = False
        else:
            loading = self.panel.is_detail_pending(request)
        self.query_one("#diff-loading", GitHubLoading).display = loading
        self.query_one("#diff-body", Horizontal).display = not loading
        if not loading:
            self._diff()
            self.query_one(_DiffHeader).refresh(layout=True)
            self.query_one(_DiffFileList).refresh(layout=True)
            self.query_one(_DiffCard).refresh(layout=True)

    def _pr_detail(self) -> PullRequestDetail | None:
        pr = self.panel.viewed
        if pr is None:
            return None
        raw = self.panel.detail_for(pr)
        if isinstance(raw, PullRequestDetail):
            return raw
        return None

    def _diff(self) -> PullRequestDiff | None:
        request = self.panel.viewed_diff
        if request is None:
            return None
        raw = self.panel.detail_for(request)
        if not isinstance(raw, PullRequestDiff):
            return None
        changed = self._sync_selection(request, raw.files)
        if changed:
            self._show_selection()
        return raw

    def _sync_selection(self, request: DiffRequest, files: tuple[FileDiff, ...]) -> bool:
        if request is not self._shown_request:
            self._shown_request = request
            self.selected_index = 0
            return True
        previous = self.selected_index
        if not files:
            self.selected_index = 0
        elif self.selected_index > len(files) - 1:
            self.selected_index = len(files) - 1
        return self.selected_index != previous

    def _selected_overflow(self) -> int:
        diff = self._diff()
        if diff is None or not diff.files:
            return 0
        file = diff.files[self.selected_index]
        row = _format_full_file_row(file, True)
        return marquee_overflow(row, _FILE_ROW_WIDTH)

    def _refresh_file_list(self) -> None:
        if not self.is_mounted:
            return
        self.query_one(_DiffFileList).refresh(layout=True)

    def _show_selection(self) -> None:
        self.marquee.reset()
        if not self.is_mounted:
            return
        self.query_one("#diff-card-scroll", VerticalScroll).scroll_home(animate=False)
        # Rows start below the card's top border and sit two lines apart: each file row is
        # followed by a blank spacer line.
        row_region = Region(0, 1 + self.selected_index * 2, 1, 1)
        files_scroll = self.query_one("#diff-files-scroll", VerticalScroll)
        files_scroll.scroll_to_region(row_region, animate=False)

    def render_header(self) -> RenderableType:
        pr = self.panel.viewed
        if pr is None:
            return Text()
        colors = self.panel.status_colors()
        parts: list[RenderableType] = [Text(_BACK_HINT, style="dim"), Text()]
        parts.extend(_format_header_lines(pr, self._diff(), self._pr_detail(), colors))
        return Group(*parts)

    def render_file_list(self) -> RenderableType:
        diff = self._diff()
        if diff is None or not diff.files:
            return Text()
        rows: list[RenderableType] = []
        for index, file in enumerate(diff.files):
            if rows:
                rows.append(Text())
            rows.append(_format_file_row(file, index == self.selected_index, self.marquee.offset))
        count = _format_files_count(diff)
        title = format_card_title(f"files ({count})")
        return format_card(title, rows)

    def render_card(self) -> RenderableType:
        diff = self._diff()
        if diff is not None:
            if not diff.files:
                return Text("no changes", style="dim")
            colors = self.panel.status_colors()
            selected = diff.files[self.selected_index]
            return _format_file_card(selected, colors)
        request = self.panel.viewed_diff
        error = None
        if request is not None:
            error = self.panel.detail_error_for(request)
        if error is not None:
            return Text(f"could not load: {error}")
        return Text("loading…", style="dim")

    def render_view(self) -> RenderableType:
        pr = self.panel.viewed
        if pr is None:
            return Text()
        parts: list[RenderableType] = [self.render_header(), Text()]
        parts.append(self.render_file_list())
        parts.append(Text())
        parts.append(self.render_card())
        return Group(*parts)

    def content_lines(self) -> list[str]:
        """render_view flattened to plain text, so the two cannot drift apart."""
        pr = self.panel.viewed
        if pr is None:
            return []
        return plain_lines(self.render_view())

    def action_next_file(self) -> None:
        diff = self._diff()
        if diff is None or not diff.files:
            return
        if self.selected_index < len(diff.files) - 1:
            self.selected_index += 1
            self._show_selection()
            self.panel.refresh()

    def action_previous_file(self) -> None:
        diff = self._diff()
        if diff is None or not diff.files:
            return
        if self.selected_index > 0:
            self.selected_index -= 1
            self._show_selection()
            self.panel.refresh()

    def action_open_in_github(self) -> None:
        pr = self.panel.viewed
        if pr is None:
            return
        webbrowser.open(pr.url)

    def action_back_to_pull_request(self) -> None:
        self.panel.close_diff()

"""The pull request view: one pull request's full story, opened from the inbox."""

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
from textual.containers import VerticalScroll
from textual.widgets import Static

from smorg.integrations.github.source import (
    ABSENT_COUNT,
    CheckSummary,
    Comment,
    Newest,
    PullRequest,
    PullRequestDetail,
    Review,
)
from smorg.shell.format import age
from smorg.shell.markdown import Markdown
from smorg.shell.panel import ScrollGutter

if TYPE_CHECKING:
    from smorg.integrations.github.panel import GitHubPanel

_BACK_HINT = "‹ esc — inbox"
_CARD_BORDER_STYLE = "dim"


def _has_any[T](shown: Newest[T]) -> bool:
    return bool(shown.items) or shown.hidden > 0 or shown.hidden_is_lower_bound


def _format_hidden_line[T](shown: Newest[T], noun: str) -> Text:
    """(hidden=1, "review") -> "… 1 earlier review"

    (hidden=1 at the cap, "review") -> "… 1+ earlier reviews"
    """
    if shown.hidden == 1 and not shown.hidden_is_lower_bound:
        label = noun
    else:
        label = f"{noun}s"
    if shown.hidden_is_lower_bound:
        count = f"{shown.hidden}+"
    else:
        count = str(shown.hidden)
    return Text(f"… {count} earlier {label}", style="dim")


def _format_review_label(state: str) -> str:
    """ "CHANGES_REQUESTED" -> "changes requested" """
    return state.replace("_", " ").casefold()


def _format_review_line(review: Review) -> Text:
    line = Text(style="dim")
    if review.author:
        author = review.author
    else:
        author = "someone"
    line.append(author)
    line.append(" · ")
    line.append(_format_review_label(review.state))
    if review.submitted_at is not None:
        line.append(" · ")
        line.append(age(review.submitted_at))
    return line


def _format_comment_heading(comment: Comment) -> Text:
    line = Text(style="dim")
    if comment.author:
        author = comment.author
    else:
        author = "someone"
    line.append(author)
    if comment.submitted_at is not None:
        line.append(" · ")
        line.append(age(comment.submitted_at))
    return line


def _format_card(title: Text, body: list[RenderableType]) -> Card:
    return Card(
        Group(*body),
        title=title,
        title_align="left",
        box=box.ROUNDED,
        border_style=_CARD_BORDER_STYLE,
        padding=(0, 1),
    )


def _format_header_lines(pr: PullRequest, detail: PullRequestDetail | None) -> list[RenderableType]:
    title = Text(pr.title, style="bold")
    meta = Text(style="dim")
    meta.append(f"{pr.repository}#{pr.number} · ")
    if pr.author:
        meta.append(f"{pr.author} · ")
    meta.append(str(pr.category))
    lines: list[RenderableType] = [title, meta]
    if detail is None:
        return lines
    stats = _format_stats_line(detail)
    if stats is not None:
        lines.append(stats)
    if detail.reviewers:
        lines.append(Text(f"waiting on {' · '.join(detail.reviewers)}", style="dim"))
    checks = detail.checks
    if not checks.available:
        lines.append(Text("no checks", style="dim"))
    elif checks.failed == 0 and checks.running == 0 and checks.passed > 0:
        lines.append(_format_all_green(checks))
    return lines


def _format_stats_line(detail: PullRequestDetail) -> Text | None:
    counts = detail.counts
    segments: list[Text] = []
    if detail.head and detail.base:
        segments.append(Text(f"{detail.head} → {detail.base}", style="dim"))
    if counts.additions != ABSENT_COUNT:
        segments.append(Text(f"+{counts.additions}", style="green"))
    if counts.deletions != ABSENT_COUNT:
        segments.append(Text(f"−{counts.deletions}", style="red"))
    if counts.changed_files != ABSENT_COUNT:
        if counts.changed_files == 1:
            noun = "file"
        else:
            noun = "files"
        segments.append(Text(f"{counts.changed_files} {noun}", style="dim"))
    if not segments:
        return None
    line = Text()
    for index, segment in enumerate(segments):
        if index > 0:
            line.append(" · ", style="dim")
        line.append_text(segment)
    return line


def _format_all_green(checks: CheckSummary) -> Text:
    line = Text()
    line.append("✓ ", style="green")
    if checks.truncated:
        line.append(f"{checks.passed}+ checks passed", style="dim")
    else:
        line.append(f"all {checks.passed} checks passed", style="dim")
    return line


def _format_checks_card(checks: CheckSummary) -> Card:
    parts = ["checks"]
    if checks.failed:
        parts.append(f"{checks.failed} failed")
    if checks.passed:
        parts.append(f"{checks.passed} passed")
    if checks.running:
        parts.append(f"{checks.running} running")
    label = " · ".join(parts)
    if checks.truncated:
        label = f"{label} · …"
    if checks.failed:
        title = Text(label, style="bold red")
    else:
        title = Text(label, style="bold yellow")
    body: list[RenderableType] = []
    for name in checks.failed_names:
        line = Text()
        line.append("✗ ", style="red")
        line.append(name)
        body.append(line)
    if checks.hidden_failed:
        body.append(Text(f"… {checks.hidden_failed} more failed", style="dim"))
    if not body:
        body.append(Text("all passing so far", style="dim"))
    return _format_card(title, body)


def _format_description_card(detail: PullRequestDetail) -> Card:
    if detail.body:
        body = detail.body
    else:
        body = "no description"
    # Markdown() interprets its input as CommonMark, not Rich's own "[style]" markup, so a
    # hostile "[red]x[/red]" body can't style or hide anything.
    content = Markdown(body, code_theme="ansi_dark")
    return _format_card(Text("description", style="bold"), [content])


def _format_reviews_card(reviews: Newest[Review]) -> Card:
    body: list[RenderableType] = []
    if reviews.hidden or reviews.hidden_is_lower_bound:
        body.append(_format_hidden_line(reviews, "review"))
    for review in reviews.items:
        body.append(_format_review_line(review))
    title = Text(f"reviews ({len(reviews.items)})", style="bold")
    return _format_card(title, body)


def _format_comments_card(comments: Newest[Comment]) -> Card:
    body: list[RenderableType] = []
    if comments.hidden or comments.hidden_is_lower_bound:
        body.append(_format_hidden_line(comments, "comment"))
    for comment in comments.items:
        if body:
            body.append(Text())
        body.append(_format_comment_heading(comment))
        if comment.body:
            body.append(Markdown(comment.body, code_theme="ansi_dark"))
    title = Text(f"comments ({len(comments.items)})", style="bold")
    return _format_card(title, body)


def _format_sections(detail: PullRequestDetail) -> list[RenderableType]:
    parts: list[RenderableType] = []
    checks = detail.checks
    if checks.available and (checks.failed or checks.running):
        parts.append(_format_checks_card(checks))
        parts.append(Text())
    parts.append(_format_description_card(detail))
    if _has_any(detail.reviews):
        parts.append(Text())
        parts.append(_format_reviews_card(detail.reviews))
    if _has_any(detail.comments):
        parts.append(Text())
        parts.append(_format_comments_card(detail.comments))
    return parts


class _PullRequestBody(Static):
    """Draws the pull request view's content; owns no state of its own."""

    DEFAULT_CSS = """
    _PullRequestBody { height: auto; }
    """

    def __init__(self, view: GitHubPullRequestView) -> None:
        # markup off: titles and bodies carry server-controlled text, so a hostile value
        # can't style, hide, or garble the view via Rich markup.
        super().__init__(markup=False, id="pull-request-body")
        self._view = view

    def render(self) -> RenderResult:
        pr = self._view.panel.viewed
        if pr is None:
            return Text()
        return self._view.render_view(pr)


class GitHubPullRequestView(VerticalScroll):
    BINDINGS = [
        Binding("o", "open_in_github", "open in GitHub", show=False),
        Binding("r", "reload", "reload this pull request", show=False),
        Binding("escape", "back_to_inbox", "back to inbox", show=False),
    ]

    DEFAULT_CSS = """
    GitHubPullRequestView {
        align-horizontal: center;
        scrollbar-size-vertical: 0;
    }
    GitHubPullRequestView > #pull-request-body { width: 100%; max-width: 120; }
    """

    def __init__(self, panel: GitHubPanel) -> None:
        super().__init__()
        self.panel = panel

    def compose(self) -> ComposeResult:
        yield _PullRequestBody(self)
        yield ScrollGutter()

    def refresh_content(self) -> None:
        if self.is_mounted:
            self.query_one(_PullRequestBody).refresh(layout=True)

    def render_view(self, pr: PullRequest) -> RenderableType:
        raw = self.panel.detail_for(pr)
        error = self.panel.detail_error_for(pr)
        if isinstance(raw, PullRequestDetail):
            detail = raw
        else:
            detail = None
        parts: list[RenderableType] = [Text(_BACK_HINT, style="dim"), Text()]
        parts.extend(_format_header_lines(pr, detail))
        parts.append(Text())
        if detail is not None:
            parts.extend(_format_sections(detail))
        elif error is not None:
            parts.append(Text(f"could not load: {error}"))
        else:
            parts.append(Text("loading…", style="dim"))
        return Group(*parts)

    def content_lines(self) -> list[str]:
        """render_view flattened to plain text, so the two cannot drift apart."""
        pr = self.panel.viewed
        if pr is None:
            return []
        console = Console(width=80, file=io.StringIO(), force_terminal=False)
        with console.capture() as capture:
            console.print(self.render_view(pr))
        return capture.get().splitlines()

    def action_open_in_github(self) -> None:
        pr = self.panel.viewed
        if pr is None:
            return
        webbrowser.open(pr.url)

    def action_reload(self) -> None:
        self.panel.reload_viewed()

    def action_back_to_inbox(self) -> None:
        self.panel.close_pull_request()

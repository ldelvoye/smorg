"""Rendering markdown the way this app wants it, for any panel to reuse.

rich.markdown.Markdown's own inline-code and link styles assume a dark terminal and truecolor
rendering; Markdown here restyles both to stay legible on either theme using ANSI-named colors
only, and underlines a code span that names a real file or directory on disk, the same hint a
terminal gives before a cmd/ctrl-click. Headings and table chrome go monochrome, fenced code
sits behind a dim left bar, and raw HTML blocks render their flattened text instead of vanishing.
"""

from __future__ import annotations

import functools
from pathlib import Path

from markdown_it.token import Token
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import CodeBlock, Heading, MarkdownElement
from rich.markdown import Markdown as _RichMarkdown
from rich.segment import Segment
from rich.style import Style
from rich.syntax import Syntax
from rich.theme import Theme

from smorg.core.text import flatten_html

_INLINE_CODE_STYLE = Style(bold=True, color="cyan")
_LOCAL_PATH_STYLE = _INLINE_CODE_STYLE + Style(underline=True)
_LINK_STYLE = Style(color="bright_blue", underline=True)
_MARKDOWN_THEME = Theme(
    {
        "markdown.code": _INLINE_CODE_STYLE,
        "markdown.link": _LINK_STYLE,
        "markdown.link_url": _LINK_STYLE,
        "markdown.h1": Style(bold=True, underline=True),
        "markdown.h2": Style(bold=True),
        "markdown.h3": Style(bold=True),
        "markdown.h4": Style(bold=True, dim=True),
        "markdown.h5": Style(bold=True, dim=True),
        "markdown.h6": Style(bold=True, dim=True),
        "markdown.table.border": Style(dim=True),
        "markdown.table.header": Style(bold=True),
    }
)

_MAX_LOCAL_PATH_LENGTH = 256


@functools.lru_cache(maxsize=256)
def is_local_path(text: str) -> bool:
    """Whether `text` names a file or directory that actually exists."""
    if not text or len(text) > _MAX_LOCAL_PATH_LENGTH or "\n" in text:
        return False
    for candidate in {text, text.rstrip("/")}:
        if candidate and Path(candidate).expanduser().exists():
            return True
    return False


def _underline_if_local_path(segment: Segment) -> Segment:
    if segment.style == _INLINE_CODE_STYLE and is_local_path(segment.text):
        return Segment(segment.text, _LOCAL_PATH_STYLE, segment.control)
    return segment


class _PlainHeading(Heading):
    """A heading drawn left-aligned in the theme's style — no centering, no panel."""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        text = self.text
        text.justify = "left"
        yield text


class _BarredCodeBlock(CodeBlock):
    """A fenced block behind a dim left bar, highlighting kept, wrapped lines barred too."""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        code = str(self.text).rstrip()
        syntax = Syntax(
            code, self.lexer_name, theme=self.theme, word_wrap=True, background_color="default"
        )
        inner_width = max(options.max_width - 2, 10)
        lines = console.render_lines(syntax, options.update_width(inner_width), pad=False)
        bar = Segment("▎ ", console.get_style("dim"))
        new_line = Segment.line()
        for line in lines:
            yield bar
            yield from line
            yield new_line


class _HtmlBlock(MarkdownElement):
    """A raw-HTML block rendered as its flattened text instead of dropped."""

    @classmethod
    def create(cls, markdown: _RichMarkdown, token: Token) -> _HtmlBlock:
        return cls(token.content)

    def __init__(self, content: str) -> None:
        self._content = content

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        flattened = flatten_html(self._content)
        if flattened:
            yield Markdown(flattened)


class Markdown(_RichMarkdown):
    """rich.markdown.Markdown with this app's code/link theme and real local paths underlined."""

    elements = {
        **_RichMarkdown.elements,
        "heading_open": _PlainHeading,
        "fence": _BarredCodeBlock,
        "code_block": _BarredCodeBlock,
        "html_block": _HtmlBlock,
    }

    def __init__(self, markup: str, **kwargs: object) -> None:
        kwargs.setdefault("code_theme", "ansi_dark")
        super().__init__(markup, **kwargs)  # type: ignore[arg-type]

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        console.push_theme(_MARKDOWN_THEME)
        try:
            rendered = list(super().__rich_console__(console, options))
        finally:
            console.pop_theme()
        for item in rendered:
            if isinstance(item, Segment):
                yield _underline_if_local_path(item)
            else:
                yield item

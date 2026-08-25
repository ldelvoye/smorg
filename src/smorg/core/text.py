"""Making text that arrived over the network safe to put on a screen."""

from __future__ import annotations

import re
from html.parser import HTMLParser


def _strip_unprintable(text: str) -> str:
    return "".join(character for character in text if character.isprintable())


def sanitize_line(value: str, limit: int = 120) -> str:
    trimmed = _strip_unprintable(value)[:limit]
    if not trimmed:
        return "(unspecified)"
    return trimmed


def sanitize_block(value: str, limit: int | None = 4000) -> str:
    """`sanitize_line()` for multi-line text: each line sanitized on its own, newlines kept, the cap
    applied to the whole block; empty stays empty.

    limit=None skips capping, for a caller that must sanitize before its own shape-sensitive
    processing (e.g. unwrapping paired tags).
    """
    lines = [_strip_unprintable(line) for line in value.split("\n")]
    sanitized = "\n".join(lines)
    if limit is None:
        return sanitized
    return sanitized[:limit]


def truncate(value: str, limit: int) -> str:
    """value truncated to `limit` characters, with a visible marker when it cuts; without one a
    cut would read as the real ending.
    """
    if len(value) <= limit:
        return value
    return value[:limit] + "\n\n… (truncated)"


class _HtmlFlattener(HTMLParser):
    """Collects a fragment's text, keeping anchors as markdown links; comments vanish."""

    _BREAKING_TAGS = ("br", "p", "div", "li", "tr")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []
        elif tag in self._BREAKING_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            text = "".join(self._link_text).strip()
            href = self._href
            self._href = None
            self._link_text = []
            if href and text:
                self.parts.append(f"[{text}]({href})")
            else:
                self.parts.append(text)
        elif tag in ("p", "div"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._link_text.append(data)
        else:
            self.parts.append(data)


def flatten_html(text: str) -> str:
    """Markdown-friendly text from an HTML fragment: tags unwrapped, comments dropped,
    anchors kept as links. Text without tags comes back unchanged.
    """
    if "<" not in text:
        return text
    flattener = _HtmlFlattener()
    flattener.feed(text)
    flattener.close()
    flattened = "".join(flattener.parts)
    collapsed = re.sub(r"\n{3,}", "\n\n", flattened)
    return collapsed.strip()

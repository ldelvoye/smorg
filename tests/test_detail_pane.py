"""The split detail pane's machinery, exercised through a minimal test-only panel."""

import io
from datetime import UTC, datetime

import pytest
from rich.console import Console, Group
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static

from smorg.core.contract import Item
from smorg.core.state import SeenState
from smorg.shell.detail_pane import SplitDetailPanel
from smorg.shell.markdown import Markdown, is_local_path
from smorg.shell.panel import PanelState, ScrollGutter

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


class _DetailPanel(SplitDetailPanel):
    BINDINGS = [
        Binding("up", "cursor_up", "select", show=False),
        Binding("down", "cursor_down", "select", show=False),
        Binding("enter", "toggle_detail", "view details", show=False),
        Binding("shift+up", "scroll_detail_up", "scroll details", show=False),
        Binding("shift+down", "scroll_detail_down", "scroll details", show=False),
    ]
    can_focus = True

    def __init__(self) -> None:
        super().__init__()
        self.cursor = 0

    def selected_item(self) -> Item | None:
        if not self.items:
            return None
        index = min(self.cursor, len(self.items) - 1)
        return self.items[index]

    def render_detail(self, item: Item, detail: object):
        if isinstance(detail, str):
            return Group(Text(item.id), Markdown(detail))
        return super().render_detail(item, detail)

    def action_cursor_down(self) -> None:
        self.cursor = (self.cursor + 1) % max(len(self.items), 1)
        self.refresh()

    def action_cursor_up(self) -> None:
        self.cursor = (self.cursor - 1) % max(len(self.items), 1)
        self.refresh()


class _Harness(App[None]):
    def __init__(self, panel: _DetailPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


def item(identifier: str = "ENG-1") -> Item:
    return Item(id=identifier, updated_at=NOW, url=f"https://x/{identifier}")


def panel_with(*items: Item) -> _DetailPanel:
    panel = _DetailPanel()
    panel.state = PanelState.READY
    panel.items = items
    panel.seen = SeenState({})
    panel.integration_id = "test"
    return panel


def _overflowing_description(lines: int = 80) -> str:
    """`lines` paragraphs, blank-line-separated so each stays its own Markdown
    paragraph instead of reflowing into one soft-wrapped block — this keeps
    the rendered row count real regardless of viewport height.
    """
    return "\n\n".join(f"line {index}" for index in range(lines))


def region_text(panel: _DetailPanel) -> str:
    content = panel.query_one("#detail-content", Static)
    # Static in this Textual version exposes the raw value passed to update()
    # via `.content` (`.renderable` no longer exists). The hint/error states
    # are a bare Text; loaded issue detail is a rich.console.Group (header
    # Text plus rich.markdown.Markdown), which has no `.plain` of its own —
    # rendering it through a real Console gets the string a reader would see.
    value = content.content
    if isinstance(value, Text):
        return value.plain
    buffer = io.StringIO()
    Console(width=80, file=buffer, force_terminal=False).print(value)
    return buffer.getvalue()


async def open_detail(pilot, panel):
    panel.focus()
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_enter_opens_the_detail_region_in_a_loading_state():
    panel = panel_with(item("ENG-1"))
    requested: list = []
    async with _Harness(panel).run_test() as pilot:
        panel.post_message = _capture(panel, requested)  # see helper below
        await open_detail(pilot, panel)

        region = panel.query_one("#detail", VerticalScroll)
        assert panel.detail_open is True
        assert region.has_class("-open")
        assert "loading" in region_text(panel)
    assert len(requested) == 1 and requested[0].item.id == "ENG-1"


def _capture(panel, into):
    original = type(panel).post_message

    def wrapped(message):
        if isinstance(message, panel.DetailRequested):
            into.append(message)
        return original(panel, message)

    return wrapped


@pytest.mark.asyncio
async def test_show_detail_renders_the_panel_s_render_detail():
    panel = panel_with(item("ENG-1"))
    async with _Harness(panel).run_test() as pilot:
        await open_detail(pilot, panel)
        panel.show_detail(panel.detail_key(item("ENG-1")), "the description")
        await pilot.pause()
        text = region_text(panel)
    assert "ENG-1" in text
    assert "the description" in text


@pytest.mark.asyncio
async def test_enter_again_on_the_same_issue_closes_the_region():
    panel = panel_with(item("ENG-1"))
    async with _Harness(panel).run_test() as pilot:
        await open_detail(pilot, panel)
        await pilot.press("enter")
        await pilot.pause()
        assert panel.detail_open is False
        assert not panel.query_one("#detail", VerticalScroll).has_class("-open")


@pytest.mark.asyncio
async def test_moving_the_cursor_shows_a_hint_for_an_unloaded_issue():
    panel = panel_with(item("ENG-1"), item("ENG-2"))
    async with _Harness(panel).run_test() as pilot:
        await open_detail(pilot, panel)
        panel.show_detail(panel.detail_key(item("ENG-1")), "the description")
        await pilot.press("down")
        await pilot.pause()
        assert "press enter to load" in region_text(panel)

        await pilot.press("up")
        await pilot.pause()
        assert "the description" in region_text(panel)  # cache hit, no refetch


@pytest.mark.asyncio
async def test_a_detail_error_renders_in_the_region_and_enter_retries():
    panel = panel_with(item("ENG-1"))
    requested: list = []
    async with _Harness(panel).run_test() as pilot:
        panel.post_message = _capture(panel, requested)
        await open_detail(pilot, panel)
        panel.show_detail_error(panel.detail_key(item("ENG-1")), "linear is down")
        await pilot.pause()
        assert "could not load: linear is down" in region_text(panel)

        await pilot.press("enter")  # same issue: closes
        await pilot.press("enter")  # reopens: error is not cached as data, refetches
        await pilot.pause()
    assert len(requested) == 2


@pytest.mark.asyncio
async def test_a_hostile_description_is_never_interpreted_as_markup():
    panel = panel_with(item("ENG-1"))
    async with _Harness(panel).run_test() as pilot:
        await open_detail(pilot, panel)
        panel.show_detail(panel.detail_key(item("ENG-1")), "[red]x[/red]")
        await pilot.pause()
        content = panel.query_one("#detail-content", Static)
        rendered = "".join(content.render_line(y).text for y in range(content.size.height))
    assert "[red]x[/red]" in rendered


@pytest.mark.asyncio
async def test_shift_down_scrolls_an_overflowing_detail():
    long_description = _overflowing_description()
    panel = panel_with(item("ENG-1"))
    async with _Harness(panel).run_test() as pilot:
        await open_detail(pilot, panel)
        panel.show_detail(panel.detail_key(item("ENG-1")), long_description)
        await pilot.pause()
        region = panel.query_one("#detail", VerticalScroll)
        before = region.scroll_offset.y
        await pilot.press("shift+down")
        await pilot.pause()
        assert region.scroll_offset.y > before


@pytest.mark.asyncio
async def test_refresh_preserves_scroll_but_a_cursor_move_resets_it():
    long_description = _overflowing_description()
    panel = panel_with(item("ENG-1"), item("ENG-2"))
    async with _Harness(panel).run_test() as pilot:
        await open_detail(pilot, panel)
        panel.show_detail(panel.detail_key(item("ENG-1")), long_description)
        await pilot.pause()
        await pilot.press("shift+down", "shift+down", "shift+down")
        await pilot.pause()
        region = panel.query_one("#detail", VerticalScroll)
        scrolled = region.scroll_offset.y
        assert scrolled > 0

        panel.refresh()
        await pilot.pause()
        assert region.scroll_offset.y == scrolled

        await pilot.press("down")
        await pilot.pause()
        assert region.scroll_offset.y == 0


async def _render_detail_segments(description: str):
    """Open the detail pane on a single issue, load `description`, and
    return the real rendered Segments (not a bare Console.print) — needed to
    prove a style survives Textual's own rendering path, not just rich's.
    """
    panel = panel_with(item("ENG-1"))
    async with _Harness(panel).run_test() as pilot:
        await open_detail(pilot, panel)
        panel.show_detail(panel.detail_key(item("ENG-1")), description)
        await pilot.pause()
        content = panel.query_one("#detail-content", Static)
        return [
            segment
            for y in range(content.size.height)
            for segment in content.render_line(y)
            if segment.text.strip()
        ]


@pytest.mark.asyncio
async def test_inline_code_carries_no_background_through_the_real_render_path():
    """Rich's default "markdown.code" style paints a hardcoded black chip
    behind inline code, contrasting with the surrounding text's own
    (theme-dependent) background — wrong on a light terminal. Checked against
    the real Static widget (not a bare Console.print), since the fix hooks
    the console's theme stack at render time and a bare Console would not
    prove it survives Textual's own rendering path.
    """
    segments = await _render_detail_segments("plain text and `inline code` here")

    code_style = next(segment.style for segment in segments if "inline code" in segment.text)
    plain_style = next(segment.style for segment in segments if "plain text" in segment.text)
    assert code_style is not None and plain_style is not None

    # No background of its own: whatever the ambient widget background is,
    # code and plain text share it rather than code carrying a distinct chip.
    assert code_style.bgcolor == plain_style.bgcolor
    assert code_style.bold is True
    assert code_style.color is not None and code_style.color.name == "cyan"
    # The theme override targets only the "markdown.code" style name, so
    # ordinary paragraph text is unaffected — it doesn't pick up code's look.
    assert not (plain_style.bold and plain_style.color and plain_style.color.name == "cyan")


@pytest.mark.asyncio
async def test_a_linear_link_carries_the_href_as_style_link_through_the_real_render_path():
    """rich's Markdown(hyperlinks=True) — its own default — carries a link's
    href as Style.link (which Textual's strip.py turns into an OSC 8
    sequence) rather than printing the raw URL, so the visible text is just
    the label.
    """
    href = "https://linear.app/x/issue/CTRL-19"
    segments = await _render_detail_segments(f"blocked by [CTRL-19]({href}) also plain text")

    link_style = next(segment.style for segment in segments if "CTRL-19" in segment.text)
    assert link_style is not None
    assert link_style.link == href
    assert link_style.underline is True
    assert link_style.color is not None and link_style.color.name == "bright_blue"

    full_text = "".join(segment.text for segment in segments)
    assert href not in full_text


@pytest.mark.asyncio
async def test_a_local_path_code_span_is_underlined_when_the_check_is_forced_true(monkeypatch):
    monkeypatch.setattr("smorg.shell.markdown.is_local_path", lambda text: True)
    segments = await _render_detail_segments("open `src/app.py` please")

    code_style = next(segment.style for segment in segments if "src/app.py" in segment.text)
    assert code_style is not None
    assert code_style.underline is True
    # Still the same base inline-code look, just with underline added on top.
    assert code_style.bold is True
    assert code_style.color is not None and code_style.color.name == "cyan"


@pytest.mark.asyncio
async def test_a_local_path_code_span_is_not_underlined_when_the_check_is_forced_false(
    monkeypatch,
):
    monkeypatch.setattr("smorg.shell.markdown.is_local_path", lambda text: False)
    segments = await _render_detail_segments("open `src/app.py` please")

    code_style = next(segment.style for segment in segments if "src/app.py" in segment.text)
    assert code_style is not None
    assert not code_style.underline


@pytest.mark.asyncio
async def test_non_code_text_is_never_underlined_by_the_local_path_check(monkeypatch):
    monkeypatch.setattr("smorg.shell.markdown.is_local_path", lambda text: True)
    segments = await _render_detail_segments("plain text and `src/app.py` here")

    plain_style = next(segment.style for segment in segments if "plain text" in segment.text)
    assert plain_style is None or not plain_style.underline


@pytest.mark.asyncio
async def test_a_code_span_naming_a_real_file_is_underlined_via_the_actual_filesystem_check(
    tmp_path, monkeypatch
):
    """No monkeypatched is_local_path here — this exercises the real stat,
    relative to a chdir'd cwd, the same way the function resolves paths for
    real. Distinct filenames (not one a substring of the other) avoid a false
    match when picking each span's segment out by text.
    """
    (tmp_path / "existing.txt").write_text("hi")
    monkeypatch.chdir(tmp_path)
    is_local_path.cache_clear()
    try:
        segments = await _render_detail_segments("see `existing.txt` and `missing.txt`")
    finally:
        is_local_path.cache_clear()

    existing_style = next(segment.style for segment in segments if "existing.txt" in segment.text)
    missing_style = next(segment.style for segment in segments if "missing.txt" in segment.text)
    assert existing_style is not None and existing_style.underline is True
    assert missing_style is not None and not missing_style.underline


@pytest.mark.asyncio
async def test_the_gutter_shows_a_down_arrow_then_switches_to_an_up_arrow():
    long_description = _overflowing_description()
    panel = panel_with(item("ENG-1"))
    async with _Harness(panel).run_test() as pilot:
        await open_detail(pilot, panel)
        panel.show_detail(panel.detail_key(item("ENG-1")), long_description)
        await pilot.pause()
        await pilot.pause()

        gutter = panel.query_one(ScrollGutter)

        def gutter_text() -> str:
            return "".join(gutter.render_line(y).text for y in range(gutter.size.height))

        at_top = gutter_text()
        assert "↓" in at_top
        assert "↑" not in at_top

        region = panel.query_one("#detail", VerticalScroll)
        region.scroll_end(animate=False)
        await pilot.pause()

        at_bottom = gutter_text()
    assert "↑" in at_bottom
    assert "↓" not in at_bottom

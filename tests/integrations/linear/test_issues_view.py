from dataclasses import replace
from datetime import timedelta

import pytest
from rich.style import Style
from rich.text import Text
from textual.widgets import Static

from smorg.core.state import SeenState
from smorg.integrations.linear.glyphs import format_priority, status_color, status_disc
from smorg.integrations.linear.palette import accent_for_background
from smorg.integrations.linear.views.issues import LinearIssues, _format_marks, _format_row_meta
from smorg.shell.cards import CHANGED_MARK
from smorg.shell.terminal_palette import StatusColors

from .helpers import NOW, PanelHarness, issue, issues_with, panel_with

COLORS = StatusColors(red="#f85149", yellow="#d29922", green="#3fb950")


def test_issues_are_grouped_by_status():
    view = issues_with(issue("ENG-1", "In Review"), issue("ENG-2", "Todo"))
    text = "\n".join(view.content_lines())
    assert "In Review" in text
    assert "Todo" in text


def test_the_identifier_and_title_both_appear():
    view = issues_with(issue("ENG-1"))
    text = "\n".join(view.content_lines())
    assert "ENG-1" in text
    assert "title of ENG-1" in text


def test_a_changed_issue_is_marked_and_a_seen_one_is_not():
    seen = SeenState({})
    unchanged = issue("ENG-2")
    seen.mark_seen("linear", unchanged)

    view = issues_with(issue("ENG-1"), unchanged, seen=seen)
    text = "\n".join(view.content_lines())
    marked = [line for line in text.splitlines() if "●" in line]

    assert any("title of ENG-1" in line for line in marked)
    assert not any("title of ENG-2" in line for line in marked)


def test_the_open_action_returns_the_url_of_the_selected_issue():
    view = issues_with(issue("ENG-1"), issue("ENG-2"))
    view.cursor = 1
    assert view.selected_url() == "https://linear.app/x/issue/ENG-2"


# --- Owner-decision extensions: status discs, priority bars, safe styling ---


def _style_at(rendered: Text, substring: str) -> str | Style | None:
    """The style of the span covering `substring`'s position in `rendered`, if any."""
    start = rendered.plain.index(substring)
    end = start + len(substring)
    for span in rendered.spans:
        if span.start < end and span.end > start:
            return span.style
    return None


@pytest.mark.parametrize(
    ("status", "status_type", "disc", "color"),
    [
        ("In Progress", "started", "◐", COLORS.yellow),
        ("in progress", "started", "◐", COLORS.yellow),
        ("In Review", "started", "◕", COLORS.green),
        ("Todo", "unstarted", "○", "dim"),
        ("Blocked", "started", "⊘", COLORS.red),
        ("Doing The Work", "started", "◐", COLORS.yellow),
        ("Someday", "unstarted", "○", "dim"),
        ("Done", "completed", "●", "dim"),
        ("Canceled", "canceled", "⊘", "dim"),
        ("Backlog", "backlog", "◌", "dim"),
    ],
)
def test_status_disc_and_color_mapping(
    status: str, status_type: str, disc: str, color: str
) -> None:
    assert status_disc(status, status_type) == disc
    assert status_color(status, status_type, COLORS) == color


def test_priority_bars_fill_to_the_level_in_the_stage_color_with_own_glyphs_for_urgent_and_none():
    urgent = format_priority("Urgent", COLORS, COLORS.red)
    assert urgent.plain == "[!]"
    assert urgent.style == f"bold {COLORS.red}"

    high = format_priority("High", COLORS, COLORS.yellow)
    assert high.plain == "▂▄▆"
    assert high.style == COLORS.yellow

    medium = format_priority("Medium", COLORS, COLORS.green)
    assert medium.plain == "▂▄▆"
    assert medium.style == COLORS.green
    assert _style_at(medium, "▆") == "dim"

    low = format_priority("Low", COLORS, COLORS.yellow)
    assert low.plain == "▂▄▆"
    assert low.style == COLORS.yellow
    assert _style_at(low, "▄▆") == "dim"

    dim_stage = format_priority("High", COLORS, "dim")
    assert dim_stage.style == ""

    none = format_priority("", COLORS, COLORS.yellow)
    assert none.plain == "---"
    assert none.style == "dim"


def test_the_changed_mark_uses_the_indigo_accent_not_green():
    marks = _format_marks(False, True, accent_for_background(None))
    style = _style_at(marks, CHANGED_MARK)
    assert style == accent_for_background(None)
    assert style != COLORS.green


def test_the_row_meta_carries_project_and_age_and_omits_an_empty_project(monkeypatch):
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW + timedelta(hours=3))

    with_project = replace(issue("ENG-1"), project="Platform")
    assert _format_row_meta(with_project).plain == "Platform · 3h"

    without_project = replace(issue("ENG-2"), project="")
    assert _format_row_meta(without_project).plain == "3h"


def test_a_cell_is_two_lines_with_the_meta_under_the_id_column(monkeypatch):
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW + timedelta(hours=3))
    with_project = replace(issue("ENG-1"), project="Platform")
    lines = issues_with(with_project).content_lines()
    row_indexes = [index for index, line in enumerate(lines) if "ENG-1" in line]
    assert len(row_indexes) == 1
    row = lines[row_indexes[0]]
    assert "title of ENG-1" in row
    assert "◕" in row
    assert "Platform · 3h" in lines[row_indexes[0] + 1]


def test_a_light_background_picks_the_brand_indigo_and_a_dark_one_the_lighter_tint():
    assert accent_for_background((250, 250, 250)) == "#5e6ad2"
    assert accent_for_background((10, 10, 10)) == "#828fff"
    assert accent_for_background(None) == "#828fff"


# --- Stable status-group ordering ---


def test_status_groups_render_in_a_fixed_actionability_order_regardless_of_input_order():
    view = issues_with(
        issue("ENG-1", "Blocked"),
        issue("ENG-2", "Todo"),
        issue("ENG-3", "In Review"),
        issue("ENG-4", "In Progress"),
    )
    text = "\n".join(view.content_lines())
    positions = [text.index(status) for status in ("In Progress", "In Review", "Todo", "Blocked")]
    assert positions == sorted(positions)


def test_an_unknown_started_status_group_sorts_between_in_review_and_todo():
    unknown = replace(issue("ENG-5", "Doing The Work"), status_type="started")
    view = issues_with(issue("ENG-1", "Todo"), unknown, issue("ENG-2", "In Review"))
    text = "\n".join(view.content_lines())
    assert text.index("In Review") < text.index("Doing The Work") < text.index("Todo")


def test_an_unknown_unstarted_status_group_sorts_between_todo_and_blocked():
    unknown = replace(issue("ENG-5", "Someday"), status_type="unstarted")
    view = issues_with(issue("ENG-1", "Blocked"), unknown, issue("ENG-2", "Todo"))
    text = "\n".join(view.content_lines())
    assert text.index("Todo") < text.index("Someday") < text.index("Blocked")


def test_two_unknown_same_type_status_groups_sort_alphabetically():
    zebra = replace(issue("ENG-5", "Zebra Work"), status_type="started")
    alpha = replace(issue("ENG-6", "Alpha Work"), status_type="started")
    view = issues_with(zebra, alpha)
    text = "\n".join(view.content_lines())
    assert text.index("Alpha Work") < text.index("Zebra Work")


def test_rows_truncate_instead_of_wrapping():
    long_title = replace(issue("ENG-1"), title="a title far too long to fit " + "x" * 200)
    lines = issues_with(long_title).content_lines()
    rows = [line for line in lines if "ENG-1" in line]
    assert len(rows) == 1
    assert "…" in rows[0]


def test_no_issue_is_selected_when_the_panel_is_empty():
    view = issues_with()
    assert view.selected_url() is None


def test_cursor_starts_at_the_first_issue():
    view = issues_with(issue("ENG-1"), issue("ENG-2"))
    assert view.selected_url() == "https://linear.app/x/issue/ENG-1"


def test_pressing_down_moves_the_selection_to_the_next_issue():
    view = issues_with(issue("ENG-1"), issue("ENG-2"), issue("ENG-3"))
    view.action_cursor_down()
    assert view.selected_url() == "https://linear.app/x/issue/ENG-2"


def test_pressing_down_wraps_from_the_last_issue_to_the_first():
    view = issues_with(issue("ENG-1"), issue("ENG-2"))
    view.cursor = 1
    view.action_cursor_down()
    assert view.selected_url() == "https://linear.app/x/issue/ENG-1"


def test_pressing_up_wraps_from_the_first_issue_to_the_last():
    view = issues_with(issue("ENG-1"), issue("ENG-2"))
    view.action_cursor_up()
    assert view.selected_url() == "https://linear.app/x/issue/ENG-2"


def test_the_cursor_clamps_when_items_shrink():
    view = issues_with(issue("ENG-1"), issue("ENG-2"), issue("ENG-3"))
    view.cursor = 2
    view.panel.items = (issue("ENG-1"),)
    assert view.selected_url() == "https://linear.app/x/issue/ENG-1"


def test_the_selected_row_carries_the_selection_marker():
    view = issues_with(issue("ENG-1"), issue("ENG-2"))
    view.cursor = 1
    text = "\n".join(view.content_lines())
    marked = [line for line in text.splitlines() if "▸" in line]
    assert any("title of ENG-2" in line for line in marked)
    assert not any("title of ENG-1" in line for line in marked)


@pytest.mark.asyncio
async def test_pressing_the_down_key_moves_the_selection_through_the_real_binding():
    panel = panel_with(issue("ENG-1"), issue("ENG-2"))
    async with PanelHarness(panel).run_test() as pilot:
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()

        selected = panel.selected_item()
        assert selected is not None
        assert selected.url == "https://linear.app/x/issue/ENG-2"


@pytest.mark.asyncio
async def test_pressing_o_opens_the_selected_issue_and_clears_its_change_mark(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "smorg.integrations.linear.views.issues.webbrowser.open", lambda url: opened.append(url)
    )
    monkeypatch.setattr("smorg.core.state.SeenState.save", lambda self: None)

    panel = panel_with(issue("ENG-1"), issue("ENG-2"))
    async with PanelHarness(panel).run_test() as pilot:
        await pilot.pause()
        assert panel.seen.is_changed("linear", issue("ENG-1")) is True

        await pilot.press("o")
        await pilot.pause()

    assert opened == ["https://linear.app/x/issue/ENG-1"]
    assert panel.seen.is_changed("linear", issue("ENG-1")) is False


def test_a_failed_seen_save_does_not_crash_and_notifies_instead(monkeypatch):
    """write_private_file/ensure_config_dir raise OSError directly on a real disk
    failure (full disk, revoked permissions, read-only filesystem) — this is not
    wrapped in a ConfigError, so the guard around seen.save() has to catch the
    unwrapped type to actually survive one.
    """
    monkeypatch.setattr("smorg.integrations.linear.views.issues.webbrowser.open", lambda url: None)

    def refuse_save(self):
        raise OSError("No space left on device")

    monkeypatch.setattr("smorg.core.state.SeenState.save", refuse_save)

    notified: list[str] = []
    monkeypatch.setattr(
        "smorg.integrations.linear.panel.LinearPanel.notify",
        lambda self, message, **kwargs: notified.append(message),
    )

    view = issues_with(issue("ENG-1"))
    view.action_open_selected()

    assert notified == ["No space left on device"]
    assert view.panel.seen.is_changed("linear", issue("ENG-1")) is False


@pytest.mark.asyncio
async def test_a_hostile_title_is_never_interpreted_as_markup_in_the_real_render():
    hostile = replace(issue("ENG-1"), title="[red]x[/red]")
    panel = panel_with(hostile)
    async with PanelHarness(panel).run_test() as pilot:
        panel.refresh()
        await pilot.pause()
        body = panel.query_one("#body", Static)
        rendered = "".join(body.render_line(y).text for y in range(body.size.height))

    # Styled output is built as rich.text.Text with literal appends, so a title
    # that looks like markup must come out unparsed rather than styled/consumed.
    assert "[red]x[/red]" in rendered


@pytest.mark.asyncio
async def test_a_hostile_status_is_never_interpreted_as_markup_in_the_real_render():
    hostile = replace(issue("ENG-1", status="[blue]Weird[/blue]"))
    panel = panel_with(hostile)
    async with PanelHarness(panel).run_test() as pilot:
        panel.refresh()
        await pilot.pause()
        body = panel.query_one("#body", Static)
        rendered = "".join(body.render_line(y).text for y in range(body.size.height))

    assert "[blue]Weird[/blue]" in rendered


@pytest.mark.asyncio
async def test_plain_output_is_derived_from_the_styled_render():
    panel = panel_with(issue("ENG-1", "In Review"), issue("ENG-2", "Todo"))
    async with PanelHarness(panel).run_test() as pilot:
        await pilot.pause()
        view = panel.query_one(LinearIssues)
        assert "\n".join(view.content_lines()) == panel.ready_text()

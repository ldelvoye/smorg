import pytest

from smorg.core.state import SeenState
from smorg.integrations.linear.views.menu import LinearMenu
from smorg.shell.panel import PanelState

from .helpers import PanelHarness, issue, menu_with, panel_with, project, viewer


def _lines(menu: LinearMenu) -> list[str]:
    return menu.content_lines()


def _text_rows(menu: LinearMenu) -> int:
    lettered = [line for line in _lines(menu) if any(glyph.isalpha() for glyph in line)]
    return len(lettered)


def _line_with(lines: list[str], needle: str) -> str:
    for line in lines:
        if needle in line:
            return line
    raise AssertionError(needle)


@pytest.mark.asyncio
async def test_the_arrival_shows_destinations_first_and_the_whole_mark_before_the_stars():
    panel = panel_with(viewer(), issue("ENG-1"), issue("ENG-2"))
    async with PanelHarness(panel).run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        menu = panel.query_one(LinearMenu)
        menu.tick(0.0)
        text = "\n".join(_lines(menu))
        assert "issues" in text
        assert "welcome back" not in text
        assert "⣿" not in text

        menu.tick(1.0)
        partial = "".join(_lines(menu)).count("⣿")
        menu.tick(2.0)
        whole = "".join(_lines(menu)).count("⣿")
        assert 0 < partial < whole
        assert "welcome back, lucas" in "\n".join(_lines(menu))
        assert menu.twinkling is False

        menu.tick(2.5)
        assert menu.twinkling is True


@pytest.mark.asyncio
async def test_the_twinkle_waits_for_data_and_the_head_cascades_in_when_it_lands():
    panel = panel_with(viewer(), issue("ENG-1"))
    panel.state = PanelState.LOADING
    async with PanelHarness(panel).run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        menu = panel.query_one(LinearMenu)
        menu.tick(3.0)
        assert menu.twinkling is False
        panel.state = PanelState.READY
        panel.refresh()
        await pilot.pause()

        menu.tick(3.1)
        partial = _text_rows(menu)
        menu.tick(4.0)
        whole = _text_rows(menu)
        assert 0 < partial < whole
        assert menu.twinkling is False

        menu.tick(4.6)
        assert menu.twinkling is True


def test_the_flash_fires_only_when_the_changed_set_grows_and_breathe_stops_on_opening_the_list():
    seen = SeenState({})
    menu = menu_with(issue("ENG-1"), seen=seen)
    menu.refresh_content()
    assert menu.flashing is False

    menu.refresh_content()
    assert menu.flashing is False

    menu.panel.items = (viewer(), issue("ENG-1"), issue("ENG-2"))
    menu.refresh_content()
    assert menu.flashing is True
    assert menu.breathing is True

    menu.acknowledge_changes()
    assert menu.breathing is False

    menu.panel.items = (viewer(), issue("ENG-1"), issue("ENG-2"), issue("ENG-3"))
    menu.refresh_content()
    assert menu.breathing is True

    menu.panel.items = (viewer(),)
    menu.refresh_content()
    assert menu.breathing is False


@pytest.mark.parametrize(
    ("state", "message", "expected"),
    [
        (PanelState.STALE, "could not reach Linear", "showing data as of"),
        (PanelState.ERROR, "network unreachable", "could not load: network unreachable"),
    ],
)
def test_stale_and_error_read_from_the_panel_and_dim_or_cut_the_mark(state, message, expected):
    menu = menu_with(issue("ENG-1"))
    menu.panel.state = state
    menu.panel.message = message
    text = "\n".join(menu.content_lines_at(100, 32))
    assert expected in text
    styles = menu.mark_styles_at(100, 32)
    assert styles <= {menu.panel.glow().dim}
    if state is PanelState.STALE:
        assert "welcome back" in text
    if state is PanelState.ERROR:
        assert menu.mark_dot_count_at(100, 32) < menu.resting_dot_count_at(100, 32)

    menu.tick(3.0)
    menu.fetch_started()
    assert menu.twinkling is False
    sweeping = menu.mark_styles_at(100, 32)
    assert sweeping <= {menu.panel.glow().dim}


def test_an_empty_board_is_quiet():
    menu = menu_with()
    menu.tick(0.0)
    menu.tick(2.6)
    assert menu.twinkling is False
    assert "nothing assigned to you" in "\n".join(menu.content_lines_at(100, 32))


def test_the_sky_fills_the_room_to_the_right_of_the_panel_on_a_short_tab():
    menu = menu_with(issue("ENG-1"))
    lines = menu.content_lines_at(200, 14)
    right_edges = [line[160:] for line in lines]
    assert any(edge.strip() for edge in right_edges)


def test_the_projects_row_counts_current_projects_and_takes_the_mark_when_selected():
    menu = menu_with(issue("ENG-1"))
    menu.panel.items = (viewer(), project("Redis"), project("Sudo"), issue("ENG-1"))
    menu.tick(0.0)
    menu.tick(3.0)
    lines = menu.content_lines_at(100, 32)
    issues_row = _line_with(lines, "issues")
    projects_row = _line_with(lines, "projects")
    assert "▸" in issues_row and "▸" not in projects_row
    assert "projects" in projects_row and " 2" in projects_row and "coming soon" not in projects_row
    menu.action_next_destination()
    lines = menu.content_lines_at(100, 32)
    assert "▸" in _line_with(lines, "projects")

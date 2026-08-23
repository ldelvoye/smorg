from textual.containers import VerticalScroll

from smorg.shell.app import SmorgApp
from smorg.shell.panel import Panel
from smorg.shell.terminal_palette import TerminalPalette


def test_help_bindings_default_to_the_class_bindings():
    panel = Panel()
    assert list(panel.help_bindings()) == list(type(panel).BINDINGS)


def test_build_detail_region_matches_what_compose_mounts():
    region = Panel().build_detail_region()
    assert isinstance(region, VerticalScroll)
    assert region.id == "detail"
    assert region.can_focus is False


def test_the_app_exposes_the_palette_it_was_given():
    palette = TerminalPalette(
        background=(0, 0, 0), foreground=(255, 255, 255), ansi=tuple([(0, 0, 0)] * 16)
    )
    assert SmorgApp(tabs=(), palette=palette).palette is palette
    assert SmorgApp(tabs=()).palette is None

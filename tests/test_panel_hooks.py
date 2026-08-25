from datetime import UTC, datetime

from textual.containers import VerticalScroll
from textual.message import Message

from smorg.core.contract import Item
from smorg.shell.app import SmorgApp
from smorg.shell.panel import Panel, ScrollGutter
from smorg.shell.terminal_palette import TerminalPalette


def test_help_bindings_default_to_the_class_bindings():
    panel = Panel()
    assert list(panel.help_bindings()) == list(type(panel).BINDINGS)


def test_build_detail_region_matches_what_compose_mounts():
    region = Panel().build_detail_region()
    assert isinstance(region, VerticalScroll)
    assert region.id == "detail"
    assert region.can_focus is False


def test_the_scroll_gutter_is_public_for_other_scroll_regions():
    assert ScrollGutter is not None


def test_the_app_exposes_the_palette_it_was_given():
    palette = TerminalPalette(
        background=(0, 0, 0), foreground=(255, 255, 255), ansi=tuple([(0, 0, 0)] * 16)
    )
    assert SmorgApp(tabs=(), palette=palette).palette is palette
    assert SmorgApp(tabs=()).palette is None


def _item(id: str = "octocat/hello#42") -> Item:
    return Item(id=id, updated_at=datetime(2026, 8, 19, 12, 0, tzinfo=UTC), url="")


class _Recording(Panel):
    """A panel that captures what it posts instead of needing a running app."""

    def __init__(self) -> None:
        super().__init__()
        self.posted: list[Message] = []

    def post_message(self, message: Message) -> bool:
        self.posted.append(message)
        return True


def test_request_detail_posts_once_until_the_answer_lands():
    panel = _Recording()
    item = _item()

    panel.request_detail(item)
    panel.request_detail(item)

    assert len(panel.posted) == 1
    assert panel.is_detail_pending(item) is True


def test_request_detail_is_a_no_op_when_cached():
    panel = _Recording()
    item = _item()
    panel.show_detail(Panel.detail_key(item), object())

    panel.request_detail(item)

    assert panel.posted == []
    assert panel.detail_for(item) is not None
    assert panel.is_detail_pending(item) is False


def test_a_detail_error_surfaces_and_a_new_request_retries():
    panel = _Recording()
    item = _item()
    panel.request_detail(item)

    panel.show_detail_error(Panel.detail_key(item), "boom")

    assert panel.detail_error_for(item) == "boom"
    assert panel.is_detail_pending(item) is False

    panel.request_detail(item)

    assert panel.detail_error_for(item) is None
    assert len(panel.posted) == 2


def test_reload_detail_drops_the_cache_and_asks_again():
    panel = _Recording()
    item = _item()
    panel.show_detail(Panel.detail_key(item), object())

    panel.reload_detail(item)

    assert panel.detail_for(item) is None
    assert panel.is_detail_pending(item) is True
    assert len(panel.posted) == 1


def test_pruning_keeps_keys_a_panel_declares_in_use():
    class _Pinning(Panel):
        def __init__(self, pinned: Item) -> None:
            super().__init__()
            self._pinned = pinned

        def detail_keys_in_use(self) -> set[tuple[str, str]]:
            return {Panel.detail_key(self._pinned)}

    item = _item()
    panel = _Pinning(item)
    panel.show_detail(Panel.detail_key(item), object())

    panel.prune_detail_cache()

    assert panel.detail_for(item) is not None

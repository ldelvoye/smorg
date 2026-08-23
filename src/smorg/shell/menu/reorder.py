"""The reorder flow: drag a configured tab up or down, then persist and apply the new order."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from smorg.core.config import ConfigError, load_config, reorder_tabs, save_config
from smorg.shell.format import merge_key_display
from smorg.shell.menu.base import ConfiguredTab, ManagementScreen, configured_tabs

_MOVE_UP = Binding("shift+up", "move_up", "move up")
_MOVE_DOWN = Binding("shift+down", "move_down", "move down")


class ReorderIntegrationList(ManagementScreen):
    """One row per configured tab; shift+up/shift+down drag the highlighted row, enter saves."""

    DEFAULT_CSS = """
    ReorderIntegrationList > .box { width: 64; }
    ReorderIntegrationList #hint { margin-top: 1; }
    """

    BINDINGS = [
        _MOVE_UP,
        _MOVE_DOWN,
        Binding("escape", "cancel", "cancel", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._tabs: list[ConfiguredTab] = list(configured_tabs())
        self._moved = False

    def compose(self) -> ComposeResult:
        rows = (Option(tab.label, id=tab.integration_id) for tab in self._tabs)
        # compact: the box carries the border, so the list drops its own frame and padding.
        options = OptionList(*rows, compact=True)
        hint = Static(self._hint_text(), markup=False, id="hint")
        box = Vertical(options, hint, classes="box")
        box.border_title = "reorder integrations"
        yield box

    def _hint_text(self) -> str:
        up_keys = self.app.get_key_display(_MOVE_UP)
        down_keys = self.app.get_key_display(_MOVE_DOWN)
        move_keys = merge_key_display(up_keys, down_keys)
        return f"{move_keys} move   enter save   esc cancel"

    def action_cancel(self) -> None:
        self.dismiss()

    def action_move_up(self) -> None:
        self._move(-1)

    def action_move_down(self) -> None:
        self._move(1)

    def _move(self, offset: int) -> None:
        options = self.query_one(OptionList)
        index = options.highlighted
        if index is None:
            return
        target = index + offset
        if target < 0 or target >= len(self._tabs):
            return
        self._tabs[index], self._tabs[target] = self._tabs[target], self._tabs[index]
        self._moved = True
        options.clear_options()
        rows = (Option(tab.label, id=tab.integration_id) for tab in self._tabs)
        options.add_options(rows)
        options.highlighted = target

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if not self._moved:
            self.dismiss()
            return
        new_order = tuple(tab.integration_id for tab in self._tabs)
        try:
            save_config(reorder_tabs(load_config(), new_order))
        except ConfigError as error:
            self.dismiss()
            self.app.notify(str(error), severity="error")
            return

        # Lazy import: at module scope this would cycle with app.py.
        from smorg.shell.app import SmorgApp

        app = self.app
        assert isinstance(app, SmorgApp)
        app.apply_tab_order(new_order)
        self.dismiss()

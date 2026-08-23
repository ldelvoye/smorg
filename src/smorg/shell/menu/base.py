"""The base every management screen shares: the option-list helper they all pick with, and the
listing of configured tabs that the remove and reorder flows both work from.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from smorg.core.config import ConfigError, TabConfig, load_config
from smorg.core.registry import UnknownIntegration, get_integration
from smorg.shell.modal import ModalBox


@dataclass(frozen=True)
class ConfiguredTab:
    integration_id: str
    display_name: str
    connection_id: str | None

    @property
    def label(self) -> str:
        if self.connection_id:
            return f"{self.display_name} ({self.connection_id})"
        return self.display_name


def _selected[T](items: Sequence[T], option_id: str | None, id_of: Callable[[T], str]) -> T | None:
    for item in items:
        if id_of(item) == option_id:
            return item
    return None


def configured_tabs() -> tuple[ConfiguredTab, ...]:
    try:
        config = load_config()
    except ConfigError:
        return ()
    tabs = tuple(_describe_tab(tab) for tab in config.tabs)
    return tabs


def _describe_tab(tab: TabConfig) -> ConfiguredTab:
    try:
        integration = get_integration(tab.integration)
    except UnknownIntegration:
        return ConfiguredTab(tab.integration, tab.integration, tab.connection)
    if tab.connection:
        connection_id = tab.connection
    else:
        connection_id = integration.manifest.connection(None).id
    return ConfiguredTab(tab.integration, integration.manifest.display_name, connection_id)


class ManagementScreen(ModalBox):
    """Base for the modal screens that manage integrations (add and remove). SmorgApp's
    check_action refuses every shell-level action while one of these is the top screen.
    """

    DEFAULT_CSS = """
    ManagementScreen > OptionList {
        max-width: 64;
        border: round $primary;
        &:focus {
            border: round $primary;
        }
    }
    """

"""The ctrl+p menu's management surface, one module per concern: `base` is what every management
screen shares, `remove`, `connect`, and `reorder` are the screen flows, and `commands` is the
palette provider that offers them.
"""

from smorg.shell.menu.base import ConfiguredTab, ManagementScreen, configured_tabs
from smorg.shell.menu.commands import ADD_COMMAND, REMOVE_COMMAND, REORDER_COMMAND, MenuCommands
from smorg.shell.menu.connect import (
    AddableIntegration,
    AddConnectionList,
    AddIntegrationList,
    ClientIdModal,
    ConnectModal,
    TokenModal,
    addable_integrations,
    connect_screen_for,
    open_tab_for,
)
from smorg.shell.menu.remove import RemoveConfirmModal, RemoveIntegrationList
from smorg.shell.menu.reorder import ReorderIntegrationList

__all__ = [
    "ADD_COMMAND",
    "REMOVE_COMMAND",
    "REORDER_COMMAND",
    "AddConnectionList",
    "AddIntegrationList",
    "AddableIntegration",
    "ClientIdModal",
    "ConfiguredTab",
    "ConnectModal",
    "ManagementScreen",
    "MenuCommands",
    "RemoveConfirmModal",
    "RemoveIntegrationList",
    "ReorderIntegrationList",
    "TokenModal",
    "addable_integrations",
    "configured_tabs",
    "connect_screen_for",
    "open_tab_for",
]

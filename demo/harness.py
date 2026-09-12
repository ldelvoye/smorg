"""Runs smorg against invented data, so a recording never shows a real workspace.

The shell looks an integration up through the registry on every call, and the registry rereads
the allowlist each time, so substituting a demo integration needs no change to shipped code.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from smorg.auth.store import Credentials
from smorg.core.contract import Item, Manifest, Unavailable
from smorg.shell.panel import Panel

FIRST_FETCH_PAUSE = 2.2
"""Seconds the first fetch takes. A recording opens on the loading art, so it has to last long
enough to read as a real connection rather than a flicker."""

FETCH_PAUSE = 0.7
"""Seconds every later fetch takes, including details. Short, because by then a viewer is
watching the navigation rather than the spinner."""


@dataclass(frozen=True)
class DemoIntegration:
    """One integration's real manifest and panel, fed from a fixed list of items."""

    manifest: Manifest
    panel_class: type[Panel]
    items: tuple[Item, ...]
    details: dict[str, Any]

    def fetch(self, credentials: Credentials, http: httpx.Client) -> Sequence[Item]:
        global _fetched_once
        if _fetched_once:
            _pause(FETCH_PAUSE)
        else:
            _fetched_once = True
            _pause(FIRST_FETCH_PAUSE)
        return self.items

    def fetch_detail(self, credentials: Credentials, http: httpx.Client, item: Item) -> Any:
        _pause(FETCH_PAUSE)
        detail = self.details.get(item.id)
        if detail is None:
            # A gap in the demo data must read like a service that could not answer, because a
            # source may only raise IntegrationError and the shell would crash on anything else.
            raise Unavailable(f"no demo detail for {item.id}")
        return detail


_fetched_once = False


def _pause(seconds: float) -> None:
    import time

    time.sleep(seconds)


def _demo_credentials(*args: object, **kwargs: object) -> Credentials:
    expires = datetime.now(UTC) + timedelta(days=365)
    return Credentials(access_token="demo", refresh_token=None, expires_at=expires, scope="demo")


def run(demos: tuple[DemoIntegration, ...]) -> None:
    """Launch the app showing only `demos`, in order, with the first tab active."""
    scratch = tempfile.mkdtemp(prefix="smorg-demo-")
    os.environ["SMORG_CONFIG_DIR"] = scratch
    os.environ["SMORG_CREDENTIAL_STORE"] = "file"

    from smorg import integrations
    from smorg.core.config import TabConfig
    from smorg.shell import app as app_module
    from smorg.shell.app import SmorgApp
    from smorg.shell.terminal_palette import query_terminal_palette

    integrations.INTEGRATIONS = demos  # type: ignore[assignment]
    app_module.credentials_for = _demo_credentials  # type: ignore[assignment]
    # The demo runs from an editable install, which earns the dev badge. A recording should show
    # what someone who installed smorg sees, so the badge stays off.
    app_module.is_dev_build = lambda: False

    tabs = tuple(TabConfig(integration=demo.manifest.id) for demo in demos)
    palette = query_terminal_palette()
    SmorgApp(tabs=tabs, palette=palette).run()

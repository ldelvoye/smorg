"""Lookup over the integration allowlist."""

from __future__ import annotations

import os

from smorg.core.contract import Integration, Manifest

EXPERIMENTAL_ENV = "SMORG_EXPERIMENTAL"


class UnknownIntegration(Exception):
    """No integration by that id is registered in this build."""


def _opted_in() -> frozenset[str]:
    """The integration ids SMORG_EXPERIMENTAL names, comma-separated: "gcal" or "gcal,slack"."""
    setting = os.environ.get(EXPERIMENTAL_ENV, "")
    opted: set[str] = set()
    for name in setting.split(","):
        trimmed = name.strip()
        if trimmed:
            opted.add(trimmed)
    return frozenset(opted)


def _by_id() -> dict[str, Integration]:
    # Imported per call, not at module load, so tests can swap the allowlist without reloading.
    from smorg import integrations

    opted_in = _opted_in()
    registry: dict[str, Integration] = {}
    seen: set[str] = set()
    for entry in integrations.INTEGRATIONS:
        manifest = entry.manifest
        identifier = manifest.id
        if identifier in seen:
            raise ValueError(f"two registered integrations share id {identifier!r}")
        seen.add(identifier)
        hidden = manifest.experimental and identifier not in opted_in
        if hidden:
            continue
        registry[identifier] = entry
    return registry


def known_integration_ids() -> tuple[str, ...]:
    registry = _by_id()
    return tuple(sorted(registry))


def manifests() -> tuple[Manifest, ...]:
    """Every registered manifest, sorted by id."""
    registry = _by_id()
    ordered = []
    for identifier in sorted(registry):
        ordered.append(registry[identifier].manifest)
    return tuple(ordered)


def get_integration(integration_id: str) -> Integration:
    registry = _by_id()
    if integration_id in registry:
        return registry[integration_id]
    if not registry:
        raise UnknownIntegration(
            f"{integration_id!r} is not supported: no integrations are registered in this build"
        )
    raise UnknownIntegration(
        f"{integration_id!r} is not a supported integration. "
        f"Available: {', '.join(sorted(registry))}"
    )

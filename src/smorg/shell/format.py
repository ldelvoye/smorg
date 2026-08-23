"""Small, integration-agnostic text formatting any shell module can reuse."""

from __future__ import annotations

from datetime import datetime

from smorg.auth.store import now


def age(moment: datetime) -> str:
    """How long ago `moment` was, as a short "5m" / "3h" / "2d" label."""
    delta = now() - moment
    # A future stamp is clock skew, and anything under a minute reads the same either way.
    if delta.total_seconds() < 60:
        return "now"
    if delta.days >= 1:
        return f"{delta.days}d"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h"
    return f"{delta.seconds // 60}m"


_SYMBOLS = {"shift+": "⇧ + ", "super+": "⌘ + "}


def merge_key_display(existing: str, new: str) -> str:
    """One row's keys, a shared modifier stated once: "⇧ + ↑" + "⇧ + ↓" -> "⇧ + ↑/↓"."""
    existing_prefix, _, existing_base = existing.rpartition(" + ")
    new_prefix, _, new_base = new.rpartition(" + ")
    if existing_prefix != new_prefix:
        return f"{existing}/{new}"
    if not existing_prefix:
        return f"{existing_base}/{new_base}"
    return f"{existing_prefix} + {existing_base}/{new_base}"


def symbolize_key_display(key: str) -> str:
    """Modifier prefixes become symbols joined with an explicit "+": "shift+x" -> "⇧ + x",
    "^p" -> "^ + p", "super+k" -> "⌘ + k".
    """
    parts = key.split("/")
    symbolized = [_symbolize_part(part) for part in parts]
    return "/".join(symbolized)


def _symbolize_part(part: str) -> str:
    for word, symbol in _SYMBOLS.items():
        if part.startswith(word):
            return symbol + _symbolize_part(part[len(word) :])
    if len(part) > 1 and part.startswith("^"):
        return f"^ + {part[1:]}"
    return part

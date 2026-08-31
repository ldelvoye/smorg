"""The persisted activity cache: what past refreshes learned about each repository.

Stored as github-activity.json in the config directory. Losing it costs one full re-probe,
so a corrupt or unreadable file starts over rather than blocking the dashboard.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from smorg.core.config import config_dir, ensure_config_dir, write_private_file
from smorg.integrations.github.source.pushed.tiers import RepoRecord

_SCHEMA_VERSION = 1
_LOCK = threading.Lock()


def cache_path() -> Path:
    return config_dir() / "github-activity.json"


def _stamp_of(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp


def _record_of(raw: object) -> RepoRecord | None:
    if not isinstance(raw, dict):
        return None
    last_probed = _stamp_of(raw.get("last_probed"))
    if last_probed is None:
        return None
    raw_activity = raw.get("last_activity")
    if raw_activity is None:
        last_activity = None
    else:
        last_activity = _stamp_of(raw_activity)
        if last_activity is None:
            return None
    return RepoRecord(last_activity=last_activity, last_probed=last_probed)


def _stamp_text(stamp: datetime | None) -> str | None:
    if stamp is None:
        return None
    return stamp.isoformat()


class ActivityCache:
    def __init__(self, records: dict[str, RepoRecord], cursor: str | None, path: Path) -> None:
        self.records = records
        self.cursor = cursor
        self._path = path

    @classmethod
    def load(cls, path: Path | None = None) -> ActivityCache:
        if path is None:
            path = cache_path()
        with _LOCK:
            try:
                raw = json.loads(path.read_text())
            except (ValueError, OSError):
                return cls({}, None, path)
        if not isinstance(raw, dict):
            return cls({}, None, path)
        if raw.get("version") != _SCHEMA_VERSION:
            return cls({}, None, path)
        records: dict[str, RepoRecord] = {}
        raw_repos = raw.get("repos")
        if isinstance(raw_repos, dict):
            for name, raw_record in raw_repos.items():
                record = _record_of(raw_record)
                if isinstance(name, str) and record is not None:
                    records[name] = record
        raw_cursor = raw.get("cursor")
        if isinstance(raw_cursor, str):
            cursor = raw_cursor
        else:
            cursor = None
        return cls(records, cursor, path)

    def save(self) -> None:
        repos = {}
        for name, record in self.records.items():
            repos[name] = {
                "last_activity": _stamp_text(record.last_activity),
                "last_probed": _stamp_text(record.last_probed),
            }
        payload = json.dumps({"version": _SCHEMA_VERSION, "repos": repos, "cursor": self.cursor})
        with _LOCK:
            if self._path == cache_path():
                ensure_config_dir()
            write_private_file(self._path, payload)

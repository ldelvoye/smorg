"""GitHub's views: full-tab looks the host panel swaps between."""

from __future__ import annotations

from enum import StrEnum


class GitHubView(StrEnum):
    MENU = "menu"
    INBOX = "inbox"

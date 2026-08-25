"""GitHub's views: full-tab looks the host panel swaps between."""

from __future__ import annotations

from enum import StrEnum

SELECTED_MARK = "▸"
CHANGED_MARK = "●"
CHANGE_STYLE = "green"


class GitHubView(StrEnum):
    MENU = "menu"
    INBOX = "inbox"
    PULL_REQUEST = "pull request"

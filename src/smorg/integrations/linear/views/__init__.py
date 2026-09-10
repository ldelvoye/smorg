"""Linear's views: full-tab looks the host panel swaps between."""

from __future__ import annotations

from enum import StrEnum


class LinearView(StrEnum):
    MENU = "menu"
    ISSUES = "issues"
    ISSUE = "issue"

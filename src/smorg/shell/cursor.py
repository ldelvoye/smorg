"""Cursor arithmetic shared by every list that steps a selection with the arrow keys."""

from __future__ import annotations


def clamp_cursor(cursor: int, count: int) -> int:
    """The cursor pulled back inside a list of `count` rows; 0 for an empty list."""
    if count == 0:
        return 0
    return min(cursor, count - 1)


def step_cursor(cursor: int, offset: int, count: int) -> int:
    """The cursor moved by `offset`, wrapping at both ends; 0 for an empty list."""
    if count == 0:
        return 0
    clamped = clamp_cursor(cursor, count)
    return (clamped + offset) % count

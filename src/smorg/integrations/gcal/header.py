"""The Google-style day header: weekday initials over date numbers, today circled in blue."""

from __future__ import annotations

from datetime import date

from rich.text import Text

from smorg.integrations.gcal.palette import RED, TODAY_BLUE

_WEEKDAY_INITIALS = ("M", "T", "W", "T", "F", "S", "S")
TODAY_FOLD = "◥"


def format_day_header(
    days: tuple[date, ...], today: date, focused: date | None, column_width: int
) -> tuple[Text, Text]:
    """Two centered rows, one initial and one number per column; today in Google blue with the
    icon's folded corner at its shoulder, `focused` underlined when it is a different day (None
    when the view marks the focused day another way)."""
    initials = Text()
    numbers = Text()
    for day in days:
        initial = _WEEKDAY_INITIALS[day.weekday()]
        number = f"{day.day:>2}"
        if day == today:
            number_style = f"bold {TODAY_BLUE}"
        elif day == focused:
            number_style = "bold underline"
        else:
            number_style = "dim"
        centered = initial.center(column_width)
        initials.append(centered, style="dim")
        cell_width = len(number) + 1
        pad_left = (column_width - cell_width) // 2
        pad_right = column_width - cell_width - pad_left
        numbers.append(" " * pad_left)
        numbers.append(number, style=number_style)
        if day == today:
            numbers.append(TODAY_FOLD, style=f"bold {RED}")
        else:
            numbers.append(" ")
        numbers.append(" " * pad_right)
    return initials, numbers

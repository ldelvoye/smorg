from rich.cells import cell_len
from rich.text import Text

from smorg.shell.format import truncating
from smorg.shell.marquee import (
    MARQUEE_HOLD_TICKS,
    MARQUEE_STYLE,
    Marquee,
    marquee_overflow,
    marquee_window,
)


def tagged_row(prefix: str, title: str, suffix: str) -> Text:
    row = Text(prefix, style="dim")
    start = len(row.plain)
    row.append(title, style="bold")
    row.stylize(MARQUEE_STYLE, start, start + len(title))
    row.append(suffix, style="dim")
    return row


def test_the_window_slides_only_the_tagged_span_and_keeps_both_ends_whole():
    row = tagged_row("○ ENG-1  ", "a title that runs far past the width", "  you")
    width = len("○ ENG-1  ") + 10 + len("  you")

    assert marquee_overflow(row, width) == len("a title that runs far past the width") - 10
    head = marquee_window(row, width, 0).plain
    assert head == "○ ENG-1  a title th  you"
    slid = marquee_window(row, width, 5).plain
    assert slid == "○ ENG-1  le that ru  you"
    tail_offset = marquee_overflow(row, width)
    tail = marquee_window(row, width, tail_offset).plain
    assert tail == "○ ENG-1   the width  you"


def test_the_window_keeps_styles_and_leaves_fitting_or_untagged_rows_alone():
    row = tagged_row("", "short", "")
    assert marquee_window(row, 20, 3).plain == "short"
    assert marquee_overflow(row, 20) == 0

    untagged = Text("a long untagged row that overflows", style="bold")
    assert marquee_window(untagged, 5, 2).plain == untagged.plain
    assert marquee_overflow(untagged, 5) == 0

    long_row = tagged_row("x ", "abcdefghij", "")
    window = marquee_window(long_row, 6, 2)
    styles = {span.style for span in window.spans}
    assert "bold" in styles

    wide = tagged_row("x ", "a🚀b🚀c and more text after", "")
    assert marquee_overflow(wide, 10) == cell_len(wide.plain) - 10
    fitted = marquee_window(wide, 10, 0)
    assert cell_len(fitted.plain) <= 10

    crowded = tagged_row("a prefix wider than ten", "title", "")
    assert marquee_overflow(crowded, 10) == 0

    clipping = truncating(tagged_row("x ", "a title that would clip with an ellipsis", ""))
    assert "…" not in marquee_window(clipping, 12, 3).plain


def test_the_marquee_rests_at_both_ends_and_bounces_between_them():
    marquee = Marquee()
    overflow = 3
    changes = []
    for _ in range(MARQUEE_HOLD_TICKS):
        changes.append(marquee.advance(overflow))
    assert changes == [False] * MARQUEE_HOLD_TICKS
    assert marquee.offset == 0

    offsets = []
    for _ in range(overflow):
        marquee.advance(overflow)
        offsets.append(marquee.offset)
    assert offsets == [1, 2, 3]

    for _ in range(MARQUEE_HOLD_TICKS):
        assert marquee.advance(overflow) is False
    marquee.advance(overflow)
    assert marquee.offset == 2

    marquee.advance(0)
    assert marquee.offset == 0

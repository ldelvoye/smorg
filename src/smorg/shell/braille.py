"""Braille drawing: a grid of sub-dots rendered as cells, each cell styled by one of its dots."""

from __future__ import annotations

from collections.abc import Mapping

from rich.text import Text

SUB_COLUMNS = 2
SUB_ROWS = 4
_BRAILLE_BASE = 0x2800

Dot = tuple[int, int]
Dots = Mapping[Dot, str]

# Unicode braille bit for each (sub-row, sub-column) inside a cell.
_DOT_BITS: dict[Dot, int] = {
    (0, 0): 0x01,
    (1, 0): 0x02,
    (2, 0): 0x04,
    (3, 0): 0x40,
    (0, 1): 0x08,
    (1, 1): 0x10,
    (2, 1): 0x20,
    (3, 1): 0x80,
}

# A cell takes the style of its centre-most lit dot, so a band edge crossing the cell
# settles on the side nearer the middle.
_CENTRE_FIRST: tuple[Dot, ...] = ((1, 0), (1, 1), (2, 0), (2, 1), (0, 0), (0, 1), (3, 0), (3, 1))


def _format_cell(dots: Dots, cell_row: int, cell_column: int) -> tuple[str, str]:
    bits = 0
    style = ""
    for offset in _CENTRE_FIRST:
        dot = (cell_row * SUB_ROWS + offset[0], cell_column * SUB_COLUMNS + offset[1])
        dot_style = dots.get(dot)
        if dot_style is None:
            continue
        bits = bits | _DOT_BITS[offset]
        if not style:
            style = dot_style
    if bits == 0:
        return " ", ""
    return chr(_BRAILLE_BASE + bits), style


def braille_lines(dots: Dots, sub_rows: int, sub_columns: int) -> list[Text]:
    """`dots` drawn as braille, one Text per cell row, `sub_columns / 2` cells wide."""
    cell_rows = (sub_rows + SUB_ROWS - 1) // SUB_ROWS
    cell_columns = (sub_columns + SUB_COLUMNS - 1) // SUB_COLUMNS
    lines: list[Text] = []
    for cell_row in range(cell_rows):
        line = Text()
        for cell_column in range(cell_columns):
            glyph, style = _format_cell(dots, cell_row, cell_column)
            if style:
                line.append(glyph, style=style)
            else:
                line.append(glyph)
        lines.append(line)
    return lines

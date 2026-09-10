"""Linear's mark: a disc cut by three diagonal gaps, and the ways light moves across it."""

from __future__ import annotations

import math
from dataclasses import dataclass

from rich.text import Text

from smorg.integrations.linear.palette import Glow
from smorg.shell.braille import SUB_COLUMNS, SUB_ROWS, Dot, Dots, braille_lines

CELL_ASPECT = 2.1
"""A cell's height over its width; line gaps put real terminals nearer 2.1 than a square 2.0."""

_BRAILLE_SUB_DOT = (0.5, 0.25)

# Three gap bands cut the disc: a solid head at the upper right, three strokes trailing to the
# lower left. Every fraction below is measured off the real mark; the 40x20 fixture pins them.
_STROKE_COUNT = 3
# The disc's radius over the canvas width: the mark leaves a margin rather than filling its box.
_RADIUS_FRACTION = 0.4531
# A gap band's width over the disc's diameter.
_GAP_WIDTH_FRACTION = 0.096
# Band centres along the screen diagonal, as fractions of the disc's reach (radius * sqrt 2).
_FIRST_BAND_FRACTION = 0.151
_BAND_SPACING_FRACTION = 0.297

# Samples per axis inside one sub-dot. A sub-dot lights when at least half of the grid lands in
# the shape, which is what keeps the rim and the gap edges off the pixel grid.
_COVERAGE_STEPS = 3

# The front runs past the tail by this fraction of the mark, so the last cells laid down still have
# time to dry before phase 1.0 has to be the resting mark.
_DRY_SPAN = 0.22
# Frame 0 is the pen touching down rather than an empty tab: a few cells at the tip of the head.
_FIRST_TOUCH = 0.015

_BAND_FRACTION = 0.125

# Above 1 the light leaves the tail fast and lingers on the head, which reads as a decay.
_DECAY_EXPONENT = 1.5


@dataclass(frozen=True)
class Mark:
    """The mark's dots on a sub-dot canvas, in leading-edge order, grouped into strokes."""

    sub_rows: int
    sub_columns: int
    dots: tuple[Dot, ...]
    positions: tuple[float, ...]
    strokes: tuple[tuple[Dot, ...], ...]

    @property
    def rows(self) -> int:
        return (self.sub_rows + SUB_ROWS - 1) // SUB_ROWS

    @property
    def columns(self) -> int:
        return (self.sub_columns + SUB_COLUMNS - 1) // SUB_COLUMNS


def _mark_radius(size: int) -> float:
    return _RADIUS_FRACTION * size


def _gap_width(size: int) -> int:
    radius = _mark_radius(size)
    diameter = 2 * radius
    exact = _GAP_WIDTH_FRACTION * diameter
    width = round(exact)
    return max(1, width)


def _gap_starts(size: int) -> list[float]:
    """Each gap band's leading edge on the head-to-tail axis, the head end first."""
    radius = _mark_radius(size)
    reach = radius * math.sqrt(2)
    width = _gap_width(size)
    starts: list[float] = []
    for index in range(_STROKE_COUNT):
        fraction = _FIRST_BAND_FRACTION + index * _BAND_SPACING_FRACTION
        centre = fraction * reach
        starts.append(centre - width / 2)
    return starts


def _in_gap(diagonal: float, starts: list[float], width: int) -> bool:
    for start in starts:
        end = start + width
        if start <= diagonal < end:
            return True
    return False


def _stretch_for(sub_dot: tuple[float, float], aspect: float = CELL_ASPECT) -> float:
    """How many times taller than wide one sub-dot is, from its size in cells and the cell
    aspect."""
    columns, rows = sub_dot
    height = rows * aspect
    return height / columns


def _mark_rows(columns: int, stretch: float = 1.0) -> int:
    """How many sub-rows tall a `columns`-wide canvas is; taller sub-dots need fewer rows."""
    exact = columns / stretch
    rows = round(exact)
    return max(1, rows)


def _canvas_columns(
    cell_rows: int, sub_rows_per_cell: int, stretch: float, *, multiple: int = 1
) -> int:
    """The canvas width in sub-columns that stands `cell_rows` terminal rows tall, snapped to a
    cell."""
    sub_rows = cell_rows * sub_rows_per_cell
    wanted = sub_rows * stretch
    wanted_steps = round(wanted / multiple)
    steps = max(1, wanted_steps)
    columns = steps * multiple
    # Snapping the width can round the derived height up past the rows asked for, which shows as
    # a blank row under the mark. Step back down until it does not.
    while columns > multiple:
        derived_rows = _mark_rows(columns, stretch)
        if derived_rows <= sub_rows:
            break
        columns -= multiple
    return columns


def _sample_offsets() -> list[tuple[float, float]]:
    offsets: list[tuple[float, float]] = []
    for row_step in range(_COVERAGE_STEPS):
        row_offset = (row_step + 0.5) / _COVERAGE_STEPS - 0.5
        for column_step in range(_COVERAGE_STEPS):
            column_offset = (column_step + 0.5) / _COVERAGE_STEPS - 0.5
            offsets.append((row_offset, column_offset))
    return offsets


def _mark_dots(size: int, stretch: float) -> tuple[list[Dot], list[float], list[list[Dot]]]:
    rows = _mark_rows(size, stretch)
    centre_row = (rows - 1) / 2
    centre_column = (size - 1) / 2
    radius = _mark_radius(size)
    limit = radius**2
    starts = _gap_starts(size)
    width = _gap_width(size)
    gap_ends = [start + width for start in starts]
    offsets = _sample_offsets()
    needed = len(offsets) / 2
    ranked: list[tuple[float, int, Dot]] = []
    for row in range(rows):
        for column in range(size):
            covered = 0
            for row_offset, column_offset in offsets:
                sample_row = (row + row_offset - centre_row) * stretch
                sample_column = column + column_offset - centre_column
                distance = sample_row**2 + sample_column**2
                if distance > limit:
                    continue
                diagonal = sample_row - sample_column
                if _in_gap(diagonal, starts, width):
                    continue
                covered += 1
            if covered < needed:
                continue
            place_row = (row - centre_row) * stretch
            place_column = column - centre_column
            axis = place_row - place_column
            ranked.append((axis, row, (row, column)))
    ranked.sort()
    dots: list[Dot] = []
    axes: list[float] = []
    bands: list[list[Dot]] = []
    for _ in range(_STROKE_COUNT + 1):
        bands.append([])
    for axis, _, dot in ranked:
        dots.append(dot)
        axes.append(axis)
        crossed = 0
        for end in gap_ends:
            if axis >= end:
                crossed += 1
        bands[crossed].append(dot)
    return dots, axes, bands


def _positions_along(axes: list[float]) -> list[float]:
    head_axis = axes[0]
    tail_axis = axes[-1]
    reach = tail_axis - head_axis
    if reach > 0:
        span = reach
    else:
        span = 1.0
    positions: list[float] = []
    for axis in axes:
        walked = axis - head_axis
        positions.append(walked / span)
    return positions


def mark_for(rows: int, aspect: float = CELL_ASPECT) -> Mark:
    """The mark that stands `rows` terminal rows tall, on a canvas sized for `aspect`."""
    stretch = _stretch_for(_BRAILLE_SUB_DOT, aspect)
    sub_columns = _canvas_columns(rows, SUB_ROWS, stretch, multiple=SUB_COLUMNS)
    sub_rows = rows * SUB_ROWS
    dots, axes, bands = _mark_dots(sub_columns, stretch)
    positions = _positions_along(axes)
    strokes: list[tuple[Dot, ...]] = []
    for band in bands:
        strokes.append(tuple(band))
    return Mark(sub_rows, sub_columns, tuple(dots), tuple(positions), tuple(strokes))


def mark_lines(mark: Mark, dots: Dots) -> list[Text]:
    """The mark drawn as braille rows, one Text per terminal row, from `dots` and their styles."""
    return braille_lines(dots, mark.sub_rows, mark.sub_columns)


def paint_resting(mark: Mark, glow: Glow) -> Dots:
    return {dot: glow.rest for dot in mark.dots}


def paint_dim(mark: Mark, glow: Glow) -> Dots:
    return {dot: glow.dim for dot in mark.dots}


def paint_draw_in(mark: Mark, glow: Glow, phase: float) -> Dots:
    total = len(mark.dots)
    touch = total * _FIRST_TOUCH
    end = total * (1.0 + _DRY_SPAN)
    span = end - touch
    front = touch + phase * span
    wet = total * _DRY_SPAN
    painted: dict[Dot, str] = {}
    for index, dot in enumerate(mark.dots):
        if index >= front:
            break
        behind = front - index
        if behind < wet:
            painted[dot] = glow.lit
        else:
            painted[dot] = glow.rest
    return painted


def _band_centre(phase: float) -> float:
    """Where the sweep's band sits on the axis: whole at the tail at phase 0, walking to the
    head."""
    half = _BAND_FRACTION / 2
    start = 1.0 - half
    walked = start - phase
    return walked % 1.0


def _in_band(position: float, centre: float) -> bool:
    gap = abs(position - centre)
    if gap > 0.5:
        gap = 1.0 - gap
    half = _BAND_FRACTION / 2
    # Strict, so at phase 0 the band's leading edge stops at the head tip instead of wrapping
    # two cells onto it.
    return gap < half


def paint_sweep(mark: Mark, glow: Glow, phase: float) -> Dots:
    centre = _band_centre(phase)
    painted: dict[Dot, str] = {}
    for index, dot in enumerate(mark.dots):
        position = mark.positions[index]
        if _in_band(position, centre):
            painted[dot] = glow.lit
        else:
            painted[dot] = glow.rest
    return painted


def _lit_share(phase: float) -> float:
    """How much of the mark, counted from the head, is still bold: all on the flash frame, none at
    rest."""
    remaining = 1 - phase
    return remaining**_DECAY_EXPONENT


def _paint_lit_prefix(dots: tuple[Dot, ...], lit: int, glow: Glow) -> dict[Dot, str]:
    painted: dict[Dot, str] = {}
    for index, dot in enumerate(dots):
        if index < lit:
            painted[dot] = glow.lit
        else:
            painted[dot] = glow.rest
    return painted


def paint_flash(mark: Mark, glow: Glow, phase: float) -> Dots:
    share = _lit_share(phase)
    total = len(mark.dots)
    lit = round(total * share)
    return _paint_lit_prefix(mark.dots, lit, glow)


def _swell(phase: float) -> float:
    """The breath: 0 at the start and the end of the cycle, 1 at its middle, eased at both ends."""
    turn = 2 * math.pi * phase
    wave = math.cos(turn)
    return (1 - wave) / 2


def paint_breathe(mark: Mark, glow: Glow, phase: float) -> Dots:
    swell = _swell(phase)
    head = mark.strokes[0]
    head_dots = len(head)
    lit = round(head_dots * swell)
    painted = _paint_lit_prefix(head, lit, glow)
    trailing = mark.strokes[1:]
    for stroke in trailing:
        for dot in stroke:
            painted[dot] = glow.rest
    return painted

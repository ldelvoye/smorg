"""The starry sky around the mark: sparse dim stars, a few of which twinkle."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from smorg.integrations.linear.palette import Glow

SKY_MIN_COLUMNS = 90
LOOP_SECONDS = 3.0

_CELLS_PER_STAR = 90
_STAR_FLOOR = 24
_TWINKLE_SHARE = 0.54
_STARS_APART = 4

# A twinkle's window as a fraction of the loop: 0.12 to 0.20 of three seconds is 0.36s to 0.6s.
_SHORTEST = 0.12
_LONGEST = 0.20

# Blank cells a star keeps between itself and anything drawn.
_MARGIN = 2

_GLYPHS = ("·", "·", "·", "⋆", "✦", "⠄")

# Where the eased hump hands a star up from dim to plain accent, and from plain to bold.
_PLAIN_AT = 0.30
_BOLD_AT = 0.72

_TRIES_PER_PLACE = 40


@dataclass(frozen=True)
class Star:
    """One star: where it sits, its glyph, and the window it twinkles in, or None if it never
    does."""

    row: int
    column: int
    glyph: str
    window: tuple[float, float] | None


def _is_clear(row: int, column: int, taken: set[tuple[int, int]], margin: int) -> bool:
    for row_step in range(-margin, margin + 1):
        for column_step in range(-margin, margin + 1):
            if (row + row_step, column + column_step) in taken:
                return False
    return True


def _free_places(taken: set[tuple[int, int]], rows: int, columns: int) -> list[tuple[int, int]]:
    """Every canvas cell with `_MARGIN` blank cells between it and `taken`."""
    free: list[tuple[int, int]] = []
    for row in range(rows):
        for column in range(columns):
            if _is_clear(row, column, taken, _MARGIN):
                free.append((row, column))
    return free


def _far_enough(place: tuple[int, int], chosen: list[tuple[int, int]], apart: int) -> bool:
    for other in chosen:
        row_gap = abs(place[0] - other[0])
        column_gap = abs(place[1] - other[1])
        if max(row_gap, column_gap) < apart:
            return False
    return True


def _pick_spread(
    places: list[tuple[int, int]], count: int, apart: int, rng: random.Random
) -> list[tuple[int, int]]:
    """`count` of `places` at random, none within `apart` of another, so the field scatters."""
    chosen: list[tuple[int, int]] = []
    limit = count * _TRIES_PER_PLACE
    attempts = 0
    while len(chosen) < count and attempts < limit:
        attempts += 1
        candidate = rng.choice(places)
        if _far_enough(candidate, chosen, apart):
            chosen.append(candidate)
    return chosen


def build_sky(taken: set[tuple[int, int]], rows: int, columns: int, seed: int) -> tuple[Star, ...]:
    """A reproducible sky clear of `taken`: sparse stars, a few with windows spread across the
    loop."""
    if columns < SKY_MIN_COLUMNS:
        return ()
    area = rows * columns
    count = max(_STAR_FLOOR, area // _CELLS_PER_STAR)
    twinkles = round(count * _TWINKLE_SHARE)
    free = _free_places(taken, rows, columns)
    rng = random.Random(seed)
    places = _pick_spread(free, count, _STARS_APART, rng)
    order = list(range(len(places)))
    rng.shuffle(order)
    chosen = order[:twinkles]
    slices: dict[int, int] = {}
    for slot, index in enumerate(chosen):
        slices[index] = slot
    stars: list[Star] = []
    for index, place in enumerate(places):
        row, column = place
        glyph = rng.choice(_GLYPHS)
        if index in slices:
            jitter = rng.random()
            start = (slices[index] + jitter) / twinkles
            duration = rng.uniform(_SHORTEST, _LONGEST)
            window = (start, duration)
        else:
            window = None
        stars.append(Star(row, column, glyph, window))
    return tuple(stars)


def _star_style(star: Star, phase: float, glow: Glow) -> str:
    if star.window is None:
        return glow.dim
    start, duration = star.window
    delta = (phase - start) % 1.0
    if delta >= duration:
        return glow.dim
    progress = delta / duration
    hump = math.sin(math.pi * progress)
    if hump >= _BOLD_AT:
        return glow.lit
    if hump >= _PLAIN_AT:
        return glow.rest
    return glow.dim


def paint_sky(
    stars: tuple[Star, ...], phase: float, glow: Glow
) -> dict[tuple[int, int], tuple[str, str]]:
    """Each star's glyph and style at `phase`; any phase below zero is rest, every star dim."""
    painted: dict[tuple[int, int], tuple[str, str]] = {}
    for star in stars:
        if phase < 0:
            style = glow.dim
        else:
            style = _star_style(star, phase, glow)
        painted[(star.row, star.column)] = (star.glyph, style)
    return painted

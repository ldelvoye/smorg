from pathlib import Path

from smorg.integrations.linear.mark import (
    _SHINE_WIDTH,
    mark_for,
    mark_lines,
    paint_draw_in,
    paint_flash,
    paint_resting,
    paint_shine,
    paint_sweep,
)
from smorg.integrations.linear.palette import Glow, glow_for_background

GLOW = Glow(rest="rest", lit="lit", dim="dim")
BLANK_BRAILLE = "⠀"


def _extent(dots) -> tuple[int, int]:
    rows = [dot[0] for dot in dots]
    columns = [dot[1] for dot in dots]
    return max(rows) - min(rows) + 1, max(columns) - min(columns) + 1


def test_the_mark_is_round_at_a_square_cell_and_shorter_at_a_tall_one():
    square = mark_for(20, aspect=2.0)
    height, width = _extent(square.dots)
    assert abs(height - width) <= 2
    tall = mark_for(20, aspect=2.1)
    tall_height, tall_width = _extent(tall.dots)
    assert tall.rows == square.rows
    assert tall_height < tall_width


def test_the_head_comes_first_and_the_three_strokes_follow_toward_the_tail():
    mark = mark_for(20, aspect=2.0)
    assert len(mark.strokes) == 4
    head = mark.strokes[0]
    assert mark.dots[0] in head
    assert len(head) > len(mark.strokes[1]) > len(mark.strokes[2]) > len(mark.strokes[3])
    assert mark.dots[-1] in mark.strokes[3]


def test_painters_keep_the_cells_and_only_move_the_light():
    mark = mark_for(20)
    resting = paint_resting(mark, GLOW)
    assert set(resting) == set(mark.dots)
    assert set(resting.values()) == {GLOW.rest}
    for painter in (paint_sweep, paint_flash, paint_shine):
        painted = painter(mark, GLOW, 0.5)
        assert set(painted) == set(mark.dots)
        assert set(painted.values()) <= {GLOW.rest, GLOW.lit}
    assert paint_flash(mark, GLOW, 1.0) == resting
    assert paint_shine(mark, GLOW, 0.9) == resting

    tail_pass = paint_shine(mark, GLOW, 0.0)
    lit_positions: list[float] = []
    for index, dot in enumerate(mark.dots):
        if tail_pass[dot] == GLOW.lit:
            lit_positions.append(mark.positions[index])
    assert lit_positions
    for position in lit_positions:
        assert position >= 1.0 - _SHINE_WIDTH


def test_the_draw_in_lands_the_head_before_the_tail_and_ends_at_rest():
    mark = mark_for(20)
    half = paint_draw_in(mark, GLOW, 0.5)
    assert 0 < len(half) < len(mark.dots)
    assert mark.dots[0] in half
    assert mark.dots[-1] not in half
    assert paint_draw_in(mark, GLOW, 1.0) == paint_resting(mark, GLOW)


def test_the_light_glow_lights_with_a_colour_not_bold_alone():
    light = glow_for_background((250, 250, 250))
    assert light.lit != f"bold {light.rest}"
    assert "#" in light.lit
    dark = glow_for_background((18, 18, 18))
    assert dark.lit != f"bold {dark.rest}"
    assert "#" in dark.lit


def test_the_mark_at_a_square_cell_matches_the_reference_art_within_dither():
    reference = (Path(__file__).parent / "fixtures" / "mark_40x20.txt").read_text().splitlines()
    mark = mark_for(20, aspect=2.0)
    lines = mark_lines(mark, paint_resting(mark, GLOW))
    assert (mark.rows, mark.columns) == (20, 40)
    mismatches = 0
    for line, expected in zip(lines, reference, strict=True):
        drawn = line.plain.ljust(40)
        wanted_line = expected.replace(BLANK_BRAILLE, " ")
        for cell, wanted in zip(drawn, wanted_line, strict=True):
            if cell != wanted:
                mismatches += 1
    assert mismatches <= 4

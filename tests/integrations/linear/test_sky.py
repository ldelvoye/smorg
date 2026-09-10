from smorg.integrations.linear.palette import Glow
from smorg.integrations.linear.sky import SKY_MIN_COLUMNS, build_sky, paint_sky

GLOW = Glow(rest="rest", lit="lit", dim="dim")


def _block(top: int, left: int, height: int, width: int) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for row in range(top, top + height):
        for column in range(left, left + width):
            cells.add((row, column))
    return cells


def test_stars_keep_clear_of_the_taken_cells_and_of_each_other():
    taken = _block(6, 12, 20, 40) | _block(9, 56, 14, 31)
    stars = build_sky(taken, rows=32, columns=100, seed=1)
    assert len(stars) >= 30
    small = build_sky(set(), rows=32, columns=100, seed=1)
    large = build_sky(set(), rows=50, columns=200, seed=1)
    assert len(large) > 2 * len(small)
    for star in stars:
        for row in range(star.row - 2, star.row + 3):
            for column in range(star.column - 2, star.column + 3):
                assert (row, column) not in taken
    places = [(star.row, star.column) for star in stars]
    for index, (row, column) in enumerate(places):
        for other_row, other_column in places[index + 1 :]:
            assert max(abs(row - other_row), abs(column - other_column)) >= 4


def test_a_narrow_tab_has_no_sky():
    assert build_sky(set(), rows=24, columns=SKY_MIN_COLUMNS - 1, seed=1) == ()


def test_at_rest_every_star_is_dim_and_the_lit_count_stays_within_a_quarter_of_the_twinklers():
    stars = build_sky(set(), rows=32, columns=100, seed=1)
    resting = paint_sky(stars, phase=-1.0, glow=GLOW)
    assert {style for _, style in resting.values()} == {GLOW.dim}
    twinkling_stars = [star for star in stars if star.window is not None]
    twinklers = len(twinkling_stars)
    cap = max(3, twinklers // 4)
    for step in range(24):
        painted = paint_sky(stars, phase=step / 24, glow=GLOW)
        lit = [style for _, style in painted.values() if style != GLOW.dim]
        assert len(lit) <= cap

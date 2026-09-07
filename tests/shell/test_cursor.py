from smorg.shell.cursor import clamp_cursor, step_cursor


def test_the_cursor_wraps_at_both_ends_and_clamps_a_stale_position():
    assert step_cursor(0, -1, 3) == 2
    assert step_cursor(2, 1, 3) == 0
    assert step_cursor(9, 1, 3) == 0
    assert step_cursor(0, 1, 0) == 0
    assert clamp_cursor(5, 3) == 2
    assert clamp_cursor(0, 0) == 0

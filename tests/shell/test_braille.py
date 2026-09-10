from smorg.shell.braille import braille_lines


def test_a_cell_draws_its_lit_dots_and_takes_the_style_of_its_centre_most_dot():
    dots = {(0, 0): "dim", (1, 0): "bold", (2, 1): "bold", (3, 1): "dim"}
    lines = braille_lines(dots, sub_rows=4, sub_columns=2)
    assert len(lines) == 1
    assert lines[0].plain == "⢣"
    styles = [str(span.style) for span in lines[0].spans]
    assert styles == ["bold"]


def test_an_unlit_cell_is_a_blank_and_rows_are_padded_to_the_canvas_width():
    lines = braille_lines({(5, 3): "x"}, sub_rows=8, sub_columns=4)
    assert [line.plain for line in lines] == ["  ", " ⠐"]

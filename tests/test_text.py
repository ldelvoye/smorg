from smorg.core.text import flatten_html, sanitize_block, sanitize_line, truncate


def test_sanitize_block_keeps_newlines_and_strips_escapes():
    hostile = "line one\n\x1b[31mline two\x1b[0m\nline three"
    assert sanitize_block(hostile) == "line one\n[31mline two[0m\nline three"


def test_sanitize_block_caps_total_length():
    assert len(sanitize_block("x" * 5000)) == 4000


def test_sanitize_block_of_empty_is_empty():
    assert sanitize_block("") == ""


def test_sanitize_block_with_no_limit_is_untruncate():
    assert len(sanitize_block("x" * 5000, limit=None)) == 5000


def test_sanitize_line_still_flattens_everything():
    assert "\n" not in sanitize_line("a\nb")


def test_truncate_leaves_under_limit_text_unchanged():
    assert truncate("short", limit=100) == "short"


def test_truncate_at_exactly_the_limit_is_unchanged():
    assert truncate("x" * 5, limit=5) == "x" * 5


def test_truncate_marks_a_cut_with_a_visible_trailing_marker():
    result = truncate("x" * 10, limit=5)
    assert result == "xxxxx\n\n… (truncated)"


def test_flatten_html_unwraps_tags_and_keeps_anchors_as_links():
    raw = '<!-- linear-linkback -->\n<p><a href="https://linear.app/i/X-1">X-1</a></p>'

    assert flatten_html(raw) == "[X-1](https://linear.app/i/X-1)"


def test_flatten_html_leaves_plain_text_alone():
    assert flatten_html("no tags, just a < b maths") == "no tags, just a < b maths"


def test_flatten_html_collapses_blank_runs():
    raw = "<div><p>one</p></div>\n\n\n<div><p>two</p></div>"

    flattened = flatten_html(raw)

    assert "one" in flattened and "two" in flattened
    assert "\n\n\n" not in flattened

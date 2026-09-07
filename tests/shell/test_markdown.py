"""Tests for the shared Markdown widget: what renders, and in whose colors."""

import io

from rich.console import Console

from smorg.shell.markdown import Markdown

SOURCE = """# Title

## Section

| a | b |
| --- | --- |
| 1 | 2 |

~~~sql
-- a comment
SELECT 1;
~~~

<p><a href="https://linear.app/i/X-1">X-1</a></p>
"""


def plain(width: int = 60) -> str:
    console = Console(width=width, file=io.StringIO(), force_terminal=False)
    with console.capture() as capture:
        console.print(Markdown(SOURCE))
    return capture.get()


def ansi(width: int = 60) -> str:
    console = Console(width=width, file=io.StringIO(), force_terminal=True, color_system="standard")
    with console.capture() as capture:
        console.print(Markdown(SOURCE))
    return capture.get()


def test_an_html_block_renders_its_text_instead_of_vanishing():
    assert "X-1" in plain()


def test_a_heading_is_not_centered():
    lines = plain().splitlines()
    title_line = next(line for line in lines if "Title" in line)

    assert title_line.startswith("Title")


def test_headings_and_tables_carry_no_ansi_color():
    """Bold/underline/dim only — rich's magenta headings and cyan table chrome are
    overridden, so the terminal palette has nothing to paint."""
    for code in ("[35m", "[36m", ";35m", ";36m"):
        assert code not in ansi()


def test_code_lines_sit_behind_the_bar():
    lines = plain().splitlines()
    code_lines = [line for line in lines if "SELECT 1;" in line or "-- a comment" in line]

    assert len(code_lines) == 2
    assert all(line.lstrip().startswith("▎") for line in code_lines)

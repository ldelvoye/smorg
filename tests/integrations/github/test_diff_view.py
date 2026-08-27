"""Tests for the diff view: rendering only, no network and no app."""

from smorg.integrations.github.source import FileDiff
from smorg.integrations.github.views.diff import (
    _format_file_counts,
    _format_file_row,
    _patch_line_style,
    _row_path_width,
)
from smorg.shell.terminal_palette import StatusColors

COLORS = StatusColors(red="#f85149", yellow="#d29922", green="#3fb950")


def test_patch_line_style_classifies_by_prefix():
    assert _patch_line_style("+added", COLORS) == COLORS.green
    assert _patch_line_style("-removed", COLORS) == COLORS.red
    assert _patch_line_style("@@ -1,2 +1,2 @@", COLORS) == "dim"
    assert _patch_line_style(" context line", COLORS) is None


DEEP = FileDiff(
    path="src/sentry/migrations/1156_organizationmemberteam_new_id_unique_not_null.py",
    previous_path="",
    additions=1,
    deletions=1,
    patch="+x",
)


def test_long_unselected_paths_keep_their_beginning_when_truncated():
    row = _format_file_row(DEEP, selected=False, marquee_offset=0).plain

    assert "src/sentry/migrations/" in row
    assert "…" in row.split(" +")[0]


def test_the_selected_long_path_slides_with_the_marquee_offset():
    row = _format_file_row(DEEP, selected=True, marquee_offset=5).plain

    window = DEEP.path[5 : 5 + _row_path_width(_format_file_counts(DEEP))]
    assert window in row

"""Tests for the diff view: rendering only, no network and no app."""

from smorg.integrations.github.views.diff import _patch_line_style
from smorg.shell.terminal_palette import StatusColors

COLORS = StatusColors(red="#f85149", yellow="#d29922", green="#3fb950")


def test_patch_line_style_classifies_by_prefix():
    assert _patch_line_style("+added", COLORS) == COLORS.green
    assert _patch_line_style("-removed", COLORS) == COLORS.red
    assert _patch_line_style("@@ -1,2 +1,2 @@", COLORS) == "dim"
    assert _patch_line_style(" context line", COLORS) is None

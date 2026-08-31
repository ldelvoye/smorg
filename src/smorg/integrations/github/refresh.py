"""GitHub's refresh indicator: contribution-graph squares in place of the default cells."""

from __future__ import annotations

from rich.text import Text

from smorg.integrations.github.palette import ramp_for_background
from smorg.shell.refresh_indicator import RefreshIndicator
from smorg.shell.terminal_palette import widget_background


class GitHubRefreshIndicator(RefreshIndicator):
    def _format_progress(self, filled: int, total: int, label: str) -> Text:
        ramp = ramp_for_background(widget_background(self))
        text = Text()
        for index in range(total):
            if index < filled:
                # The ramp has four shades; cells beyond it reuse the last one.
                style = ramp[min(index, len(ramp) - 1)]
                text.append("■ ", style=style)
            else:
                text.append("□ ", style="dim")
        text.append(" ", style="dim")
        text.append(label, style="dim")
        return text

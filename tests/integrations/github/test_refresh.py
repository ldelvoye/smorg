from __future__ import annotations

from textual.app import App, ComposeResult

from smorg.integrations.github.palette import ramp_for_background
from smorg.integrations.github.refresh import GitHubRefreshIndicator
from smorg.integrations.github.source import FETCH_PHASES


class _RefreshHarness(App[None]):
    def compose(self) -> ComposeResult:
        yield GitHubRefreshIndicator(FETCH_PHASES)


async def test_format_progress_draws_contribution_cells():
    async with _RefreshHarness().run_test() as pilot:
        indicator = pilot.app.query_one(GitHubRefreshIndicator)
        text = indicator._format_progress(3, 5, "fetching profile…")

    assert text.plain == "■ ■ ■ □ □  fetching profile…"
    ramp = ramp_for_background(None)
    filled_spans = text.spans[:3]
    filled_styles = [str(span.style) for span in filled_spans]
    assert filled_styles == list(ramp[:3])

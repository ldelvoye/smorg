import pytest

from smorg.integrations.linear.glyphs import BAR_CELLS, format_progress_bar, priority_rank


@pytest.mark.parametrize(("percent", "done"), [(0, 0), (5, 1), (52, 5), (100, 10), (140, 10)])
def test_the_bar_fills_by_tenths_rounding_half_up_and_clamps(percent, done):
    bar = format_progress_bar(percent, "#828fff")
    plain = bar.plain
    assert len(plain) == BAR_CELLS
    assert len(set(plain[:done])) <= 1 and len(set(plain[done:])) <= 1
    if 0 < done < BAR_CELLS:
        assert plain[done - 1] != plain[done]


def test_priorities_rank_urgent_first_and_none_last():
    ranks = [priority_rank(name) for name in ("Urgent", "High", "Medium", "Low", "No priority", "")]
    assert ranks == sorted(ranks)
    assert priority_rank("Urgent") < priority_rank("Low") < priority_rank("")

from rich.style import Style

from smorg.integrations.gcal.chips import format_chip, pulsed_fill
from smorg.integrations.gcal.palette import BREATH_SECONDS


def test_the_selected_chip_keeps_its_fill_and_breathes():
    peak = pulsed_fill("#039be5", 0.0)
    trough = pulsed_fill("#039be5", BREATH_SECONDS / 2)
    assert peak != trough
    assert trough == "#039be5"

    selected = format_chip("Standup", 12, "#039be5", True, False, fill=peak)
    selected_style = Style.parse(selected.style)
    assert selected_style.bgcolor is not None
    assert selected_style.bold

    unselected = format_chip("Standup", 12, "#039be5", False, False)
    unselected_style = Style.parse(unselected.style)
    assert selected_style.color == unselected_style.color

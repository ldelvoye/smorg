from datetime import UTC, datetime

import pytest

from smorg.integrations.linear.dates import target_label


@pytest.fixture
def frozen_now(monkeypatch):
    monkeypatch.setattr(
        "smorg.integrations.linear.dates.now",
        lambda: datetime(2026, 9, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("iso_date", "resolution", "expected"),
    [
        ("2027-01-31", "halfYear", "H1 2027"),
        ("2026-12-31", "quarter", "Q4 2026"),
        ("2027-01-31", "month", "Jan 2027"),
        ("2027-06-30", "year", "2027"),
        ("2027-01-31", "", "Jan 31, 2027"),
        ("2026-10-31", "day", "Oct 31"),
        ("", "halfYear", ""),
    ],
)
def test_a_target_reads_at_the_resolution_linear_gave_it(
    iso_date, resolution, expected, frozen_now
):
    assert target_label(iso_date, resolution) == expected

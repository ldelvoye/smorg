"""Target dates the way Linear resolves them: a day, a month, a quarter, a half, or a year."""

from __future__ import annotations

from datetime import date

from smorg.auth.store import now


def target_label(iso_date: str, resolution: str) -> str:
    """ "2027-01-31" at "halfYear" -> "H1 2027"; "" when there is no date."""
    if not iso_date:
        return ""
    target = date.fromisoformat(iso_date)
    if resolution == "year":
        return str(target.year)
    if resolution == "halfYear":
        half = (target.month - 1) // 6 + 1
        return f"H{half} {target.year}"
    if resolution == "quarter":
        quarter = (target.month - 1) // 3 + 1
        return f"Q{quarter} {target.year}"
    if resolution == "month":
        return f"{target.strftime('%b')} {target.year}"
    month_day = f"{target.strftime('%b')} {target.day}"
    if target.year == now().year:
        return month_day
    return f"{month_day}, {target.year}"

"""Date overrides for the weekday discipline rules described in #668."""

from datetime import date
from typing import Mapping, Sequence

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def sports_allowed_on_day(
    rules: Mapping[str, Sequence[str]], day: date,
) -> Sequence[str] | None:
    """An explicit empty rule excludes all sports. No rule is unrestricted."""
    return rules.get(day.isoformat(), rules.get(WEEKDAY_KEYS[day.weekday()]))

"""The pinned reference dates are weekday-stable on EVERY calendar day (#233)."""
from datetime import date, timedelta

import pytest

from tests.smoke._reference_dates import pinned_reference_events


pytestmark = pytest.mark.smoke


@pytest.mark.parametrize("offset", range(7), ids=lambda o: (date(2026, 7, 20) + timedelta(days=o)).strftime("%a"))
def test_events_land_on_fixed_weekdays_for_every_today(offset):
    today = date(2026, 7, 20) + timedelta(days=offset)
    b_date, a_date = pinned_reference_events(today)
    assert b_date.weekday() == 2  # Wednesday: recovery D+1/D+2 stay in-week
    assert a_date.weekday() == 6  # Sunday: a typical race day
    assert 7 <= (b_date - today).days <= 13
    assert 77 <= (a_date - today).days <= 83
    assert (a_date - b_date).days >= 60  # A stays the later plan anchor

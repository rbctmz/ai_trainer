"""Weekday-pinned event dates for reference-plan smoke tests (Issue #233).

Reference plans are built from «today», so floating offsets (`today+13`,
`today+12 weeks`) make every calendar day a NEW configuration: race-week
overlays cross different week boundaries and tests break «by themselves»
(the #163/#164 → #226 → #233 class). Pinning the race WEEKDAYS relative to
today makes the configuration identical on every calendar day:

- B race: next Wednesday at least a week out — its recovery days (D+1/D+2)
  stay inside the race week, matching the mid-week configurations the
  quantitative gates were confirmed on;
- A race: a Sunday roughly 12 weeks out — a typical race weekday whose
  pre-race week starts after a weekend, not on a long-session Monday.

Tests that deliberately probe boundary alignments (e.g. the #226
Saturday/Sunday spillover matrix) keep pinning their own weekdays instead.
"""
from __future__ import annotations

from datetime import date, timedelta


def pinned_reference_events(today: date) -> tuple[date, date]:
    """(b_date, a_date): B on next-plus-one Wednesday, A on a Sunday ~12w out."""
    b_date = today + timedelta(days=((2 - today.weekday()) % 7) + 7)
    a_date = today + timedelta(days=((6 - today.weekday()) % 7) + 7 * 11)
    return b_date, a_date

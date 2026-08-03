"""BDD gates for TD-005/D3 (#355): Garmin activity window via shared cursors.

The Garmin activity domain must use the same `sync_cursors` semantics as
Intervals: incremental window from the persistent cursor (boundary day re-synced
on purpose), bootstrap when absent, fail-closed on a corrupt cursor, and the
cursor advances only after a clean fetch+ingest pass.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from data.database import Database
from services import sync as sync_service


pytestmark = pytest.mark.smoke
_NOW = datetime(2026, 8, 3, 12, 0, 0)


class _CursorDB:
    def __init__(self, cursor):
        self.cursor = cursor
        self.calls: list[tuple[str, str, str]] = []

    def get_sync_cursor(self, provider, domain):
        return self.cursor

    def set_sync_cursor(self, provider, domain, value):
        self.calls.append((provider, domain, value))


def test_incremental_window_comes_from_cursor():
    db = _CursorDB("2026-07-25")

    window = sync_service.resolve_sync_window(db, now=_NOW)

    assert window.mode == "incremental"
    assert window.start_date.date() == datetime(2026, 7, 24).date()
    assert window.end_date.date() == _NOW.date()


def test_no_cursor_bootstraps_default_window():
    db = _CursorDB(None)

    window = sync_service.resolve_sync_window(db, now=_NOW)

    assert window.mode == "full"  # legacy bootstrap без курсора — full 30 дней
    assert window.days == sync_service.DEFAULT_SYNC_DAYS
    assert window.start_date.date() == (_NOW - timedelta(days=30)).date()


def test_full_reload_ignores_cursor():
    db = _CursorDB("2026-07-25")

    window = sync_service.resolve_sync_window(db, days=90, now=_NOW)

    assert window.mode == "full"
    assert window.days == 90


def test_bad_cursor_fails_closed():
    db = _CursorDB("not-a-date")

    with pytest.raises(ValueError):
        sync_service.resolve_sync_window(db, now=_NOW)


def test_advance_helper_writes_cursor_only_when_clean():
    db = _CursorDB(None)

    sync_service._advance_garmin_activity_cursor(db, _NOW.date(), clean=True)
    assert db.calls == [("garmin", "activities", "2026-08-03")]

    sync_service._advance_garmin_activity_cursor(db, _NOW.date(), clean=False)
    assert len(db.calls) == 1


def test_cursor_advance_loop_on_real_database(tmp_path):
    db = Database(str(tmp_path / "cursor.db"))

    first = sync_service.resolve_sync_window(db, now=_NOW)
    db.set_sync_cursor("garmin", "activities", first.end_date.date().isoformat())

    second_now = _NOW + timedelta(days=2)
    second = sync_service.resolve_sync_window(db, now=second_now)

    assert second.start_date.date() == first.end_date.date() - timedelta(days=1)
    assert second.end_date.date() == second_now.date()

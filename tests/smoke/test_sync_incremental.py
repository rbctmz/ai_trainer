from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from data.database import Database
from services import sync as sync_service


pytestmark = pytest.mark.smoke

_NOW = datetime(2026, 7, 1, 12, 0, 0)


class _StubLatestDatesDB:
    def __init__(self, latest: dict[str, str | None]) -> None:
        self._latest = latest

    def get_latest_data_dates(self) -> dict[str, str | None]:
        return self._latest


def _activity(activity_id: str, date: str, tss: float = 50.0) -> dict:
    return {
        "activity_id": activity_id,
        "date": date,
        "sport": "running",
        "duration_minutes": 60,
        "distance_km": 10.0,
        "tss": tss,
    }


def test_resolve_sync_window_explicit_days_is_full_reload():
    window = sync_service.resolve_sync_window(_StubLatestDatesDB({}), days=90, now=_NOW)

    assert window.mode == "full"
    assert window.days == 90
    assert (window.end_date - window.start_date).days == 90


def test_resolve_sync_window_empty_db_falls_back_to_default_full():
    window = sync_service.resolve_sync_window(
        _StubLatestDatesDB({"activities": None, "hrv_data": None}),
        now=_NOW,
    )

    assert window.mode == "full"
    assert window.days == sync_service.DEFAULT_SYNC_DAYS


def test_resolve_sync_window_incremental_starts_at_oldest_latest_date():
    database = _StubLatestDatesDB(
        {
            "activities": "2026-06-30",
            "hrv_data": "2026-06-28",
            "sleep_data": "2026-06-29",
            "daily_health": "2026-06-30",
        }
    )

    window = sync_service.resolve_sync_window(database, now=_NOW)

    assert window.mode == "incremental"
    # Окно начинается с самой отстающей таблицы, включая её последний день
    # (перекрытие поглощается UPDATE-путём без дублей).
    assert window.start_date.strftime("%Y-%m-%d") == "2026-06-28"
    assert window.days == 3


def test_resolve_sync_window_same_day_resync_covers_today():
    database = _StubLatestDatesDB({"activities": "2026-07-01"})

    window = sync_service.resolve_sync_window(database, now=_NOW)

    assert window.mode == "incremental"
    assert window.start_date.strftime("%Y-%m-%d") == "2026-07-01"
    assert window.days == 1


def test_resolve_sync_window_clamps_large_gap_to_default():
    database = _StubLatestDatesDB({"activities": "2025-01-01"})

    window = sync_service.resolve_sync_window(database, now=_NOW)

    assert window.mode == "incremental"
    assert window.days == sync_service.DEFAULT_SYNC_DAYS


def test_database_reports_latest_dates_per_table(tmp_path):
    database = Database(db_path=str(tmp_path / "sync_test.db"))

    database.sync_activities(
        [
            _activity("run-1", "2026-06-27 08:00:00"),
            _activity("run-2", "2026-06-29 08:00:00"),
        ]
    )
    database.sync_hrv_data({"2026-06-30": {"rmssd": 42, "stress_score": 20, "recovery_score": 70}})

    latest = database.get_latest_data_dates()

    assert latest["activities"] == "2026-06-29"
    assert latest["hrv_data"] == "2026-06-30"
    assert latest["sleep_data"] is None
    assert latest["daily_health"] is None


def test_sync_incremental_no_duplicates(tmp_path):
    database = Database(db_path=str(tmp_path / "sync_test.db"))
    # Date-safe fixtures (issue #320): stay inside the rolling 30-day window
    # used by get_activities(days=30) instead of hardcoded dates that silently
    # expire as the calendar advances.
    activity_day = (date.today() - timedelta(days=5)).isoformat()
    activities = [_activity("run-1", f"{activity_day} 08:00:00")]

    first = database.sync_activities(activities)
    second = database.sync_activities(activities)

    assert first == {"new": 1, "updated": 0, "skipped": 0}
    assert second == {"new": 0, "updated": 1, "skipped": 0}

    stored = database.get_activities()
    assert len(stored) == 1

    hrv_day = (date.today() - timedelta(days=4)).isoformat()
    hrv = {hrv_day: {"rmssd": 42, "stress_score": 20, "recovery_score": 70}}
    assert database.sync_hrv_data(hrv) == {"new": 1, "updated": 0}
    assert database.sync_hrv_data(hrv) == {"new": 0, "updated": 1}


def test_sync_status_payload_exposes_mode_and_counts():
    result = sync_service.GarminSyncResult(
        activity_result={"new": 3, "updated": 1, "skipped": 2},
        hrv_result={"new": 2, "updated": 0},
        sleep_result={"new": 1, "updated": 1},
        health_result={"new": 0, "updated": 0},
        training_status_result={"new": 0, "updated": 1},
        mode="incremental",
        days=2,
    )

    payload = sync_service.build_sync_status_payload(result)

    assert payload["mode"] == "incremental"
    assert payload["days"] == 2
    assert payload["counts"] == {"new": 6, "updated": 3, "skipped": 2}
    assert "с последней синхронизации" in payload["summary"]

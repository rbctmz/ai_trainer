from __future__ import annotations

from datetime import datetime

import pytest

from services import sync as sync_service


pytestmark = pytest.mark.smoke


class _StubGarminClient:
    def __init__(self) -> None:
        self.is_authenticated = True
        self._last_error = {"context": "activities", "message": "partial Garmin warning"}

    def get_activities(self, *_args, **_kwargs):
        return [
            {
                "activityId": "run-1",
                "startTimeLocal": "2026-01-01T10:00:00",
                "activityType": {"typeKey": "running"},
                "duration": 3600,
                "distance": 10000,
                "averageHR": 150,
            }
        ]

    def pop_last_error(self):
        error = self._last_error
        self._last_error = None
        return error

    def get_hrv_data(self, _date):
        return {"daily_rmssd": 42}

    def get_stress_data(self, _date):
        return {"avgStressLevel": 21}

    def get_body_battery_data(self, _date):
        return [{"bodyBatteryValuesArray": [[0, 76]]}]

    def get_sleep_data(self, _date):
        return {
            "calendarDate": "2026-01-02",
            "dailySleepDTO": {
                "sleepTimeSeconds": 25200,
                "deepSleepSeconds": 3600,
                "lightSleepSeconds": 16200,
                "remSleepSeconds": 5400,
                "awakeCount": 1,
                "sleepStartTimestampLocal": "2026-01-01T23:00:00",
                "sleepEndTimestampLocal": "2026-01-02T06:00:00",
            },
            "sleepScores": {
                "overall": {"value": 82},
            },
        }

    def get_daily_summary(self, _date):
        return {
            "totalSteps": 12000,
            "totalDistanceMeters": 8500,
            "activeKilocalories": 640,
            "bmrKilocalories": 1700,
        }

    def get_resting_heart_rate(self, _date):
        return {"restingHeartRate": 48}

    def get_training_status(self):
        return None

    def get_vo2_max(self):
        return None

    def get_training_readiness(self):
        return None


class _StubDatabase:
    def __init__(self) -> None:
        self.activities = None
        self.hrv = None
        self.sleep = None
        self.health = None
        self.training_status = None

    def sync_activities(self, activities):
        self.activities = activities
        return {"new": len(activities), "updated": 0, "skipped": 0}

    def sync_hrv_data(self, hrv_data):
        self.hrv = hrv_data
        return {"new": len(hrv_data), "updated": 0}

    def sync_sleep_data(self, sleep_data):
        self.sleep = sleep_data
        return {"new": len(sleep_data), "updated": 0}

    def sync_daily_health(self, health_data):
        self.health = health_data
        return {"new": len(health_data), "updated": 0}

    def sync_training_status(self, training_status):
        self.training_status = training_status
        return {"new": len(training_status), "updated": 0}


class _StubState:
    def __init__(self) -> None:
        self.garmin_client = _StubGarminClient()
        self.database = _StubDatabase()


def test_sync_service_runs_pipeline_and_emits_progress(monkeypatch: pytest.MonkeyPatch):
    state = _StubState()
    progress_updates: list[sync_service.SyncProgressUpdate] = []
    cache_cleared = False

    def fake_clear_data_caches() -> None:
        nonlocal cache_cleared
        cache_cleared = True

    monkeypatch.setattr(sync_service, "clear_data_caches", fake_clear_data_caches)

    result = sync_service.sync_garmin_data(
        state,
        days=1,
        on_progress=progress_updates.append,
    )

    assert progress_updates[0].percent == 10
    assert progress_updates[-1].percent == 100
    assert any(update.stats_message == "Найдено активностей: 1" for update in progress_updates)

    assert result.warnings == ["partial Garmin warning"]
    assert result.activity_result == {"new": 1, "updated": 0, "skipped": 0}
    assert result.hrv_result["new"] >= 1
    assert result.sleep_result["new"] >= 1
    assert result.health_result["new"] >= 1
    assert "🎯 Статус тренированности: не найден (возможно, требуется Premium подписка Garmin)" in result.details
    assert "🆕 1 новых активностей" in result.success_messages

    assert state.database.activities
    assert state.database.hrv
    assert state.database.sleep
    assert state.database.health
    assert state.database.training_status is None
    assert cache_cleared is True

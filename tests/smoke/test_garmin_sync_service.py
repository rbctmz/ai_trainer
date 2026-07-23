from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from config.settings import Settings
from data.database import Database
from services import sync as sync_service


pytestmark = pytest.mark.smoke


@pytest.fixture(autouse=True)
def _no_live_intervals_icu(monkeypatch: pytest.MonkeyPatch) -> None:
    """This file tests the Garmin sync pipeline in isolation. Without this,
    sync_garmin_data's Intervals.icu athlete-profile step (issue #102) would
    make a real network call whenever a developer's own .env happens to have
    a real INTERVALS_ICU_API_KEY configured, breaking the contributor-safe
    guarantee of this test suite."""
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", None)


class _StubGarminClient:
    def __init__(self) -> None:
        self.is_authenticated = True
        self._last_error = {"context": "activities", "message": "partial Garmin warning"}

    def get_activities(self, *_args, **_kwargs):
        return [
            {
                "activityId": "run-1",
                "startTimeLocal": "2026-01-01T10:00:00",
                "startTimeGMT": "2026-01-01T07:00:00",
                "activityType": {"typeKey": "running"},
                "duration": 3600,
                "movingDuration": 3420,
                "distance": 10000,
                "averageHR": 150,
                "activityTrainingLoad": 47.4,
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
        # Mirrors a real reported sync: morning peak of 80, drained to 16
        # by evening. A same-day resync must keep reporting the peak.
        return [
            {
                "bodyBatteryValuesArray": [
                    [1767250800000, 42],
                    [1767261600000, 80],
                    [1767296400000, 61],
                    [1767322800000, 16],
                ]
            }
        ]

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

    def get_respiration_data(self, _date):
        return {
            "dailyRespirationDTO": {
                "avgWakingRespirationValue": 13.2,
                "lowestRespirationValue": 9.1,
                "highestRespirationValue": 17.8,
            }
        }

    def get_spo2_data(self, _date):
        return {"dailySpO2DTO": {"averageSpO2": 96.5, "lowestSpO2": 92.0}}

    def get_skin_temperature_data(self, _date):
        return {"dailySkinTemperatureDTO": {"avgSkinTempCelsius": 33.2}}

    def get_training_status(self):
        return None

    def get_vo2_max(self):
        return None

    def get_training_readiness(self):
        return None


class _StubDatabase:
    """Real activity persistence + lightweight wellness capture.

    After M1 D1 the Garmin sync writes activities through the provider-link ingest
    (``write_provider_activity`` → projection), so the activity path delegates to a
    REAL embedded ``Database`` — this is what makes these tests exercise (and prove
    byte-identity of) the real ingest path. HRV/sleep/health/training-status are
    still captured in-memory for the pipeline assertions. It DELIBERATELY omits
    ``save_readiness_snapshot`` so ``sync_garmin_data`` skips the optional
    recovery-snapshot hook and the exact warnings/details assertions stay stable.
    """

    def __init__(self, real_db: Database) -> None:
        self._db = real_db
        self.hrv = None
        self.sleep = None
        self.health = None
        self.training_status = None

    # --- activity path → real provider-link ingest (M1 D1) ---
    def clean_value(self, value):
        return self._db.clean_value(value)

    def write_provider_activity(self, canonical, link, *, primary_source):
        return self._db.write_provider_activity(canonical, link, primary_source=primary_source)

    def get_latest_data_dates(self):
        return self._db.get_latest_data_dates()

    def get_activities(self, days=3650):
        return self._db.get_activities(days=days)

    # --- wellness → in-memory capture (unchanged) ---
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

    def get_athlete_profile(self):
        return None

    def save_athlete_profile(self, profile):
        pass


def _make_database(tmp_path) -> Database:
    return Database(str(tmp_path / "garmin-sync.db"))


class _StubState:
    def __init__(self, database) -> None:
        self.garmin_client = _StubGarminClient()
        self.database = database


class _FlakySleepClient(_StubGarminClient):
    def __init__(self) -> None:
        super().__init__()
        self.sleep_calls = 0

    def get_sleep_data(self, _date):
        self.sleep_calls += 1
        if self.sleep_calls == 1:
            self._last_error = {
                "context": "sleep_data",
                "message": "429 Too Many Requests from Garmin sleep endpoint",
            }
            return None
        self._last_error = None
        return super().get_sleep_data(_date)


class _FlakySleepState(_StubState):
    def __init__(self, database) -> None:
        self.garmin_client = _FlakySleepClient()
        self.database = database


def test_sync_service_runs_pipeline_and_emits_progress(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db = _make_database(tmp_path)
    state = _StubState(_StubDatabase(db))
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
    assert result.source == "garmin"
    assert result.activity_result == {"new": 1, "updated": 0, "skipped": 0}
    assert result.hrv_result["new"] >= 1
    assert result.sleep_result["new"] >= 1
    assert result.health_result["new"] >= 1
    assert "🎯 Статус тренированности: не найден (возможно, требуется Premium подписка Garmin)" in result.details
    assert "🆕 1 новых активностей" in result.success_messages

    # After M1 D1 the activity is persisted through the provider-link projection;
    # the stored row must be byte-identical to what the legacy bulk write produced.
    stored = db.get_activities(days=3650)
    assert len(stored) == 1
    stored_row = stored.iloc[0]
    assert stored_row["activity_id"] == "run-1"
    assert stored_row["tss"] == 74.0
    assert stored_row["garmin_training_load"] == 47.4
    assert stored_row["source_tss"] == 47.4
    assert stored_row["tss_method"] == "hr_tss_run"
    assert stored_row["started_at_utc"] == "2026-01-01T07:00:00Z"
    # The activity has exactly one Garmin provider-link on its own canonical.
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    links = conn.execute(
        "SELECT provider, provider_activity_id, canonical_activity_id "
        "FROM activity_provider_links"
    ).fetchall()
    conn.close()
    assert links == [("garmin", "run-1", "run-1")]

    assert state.database.hrv
    for entry in state.database.hrv.values():
        assert entry["recovery_score"] == 80
    assert state.database.sleep
    assert state.database.health
    for entry in state.database.health.values():
        assert entry["respiration_avg"] == 13.2
        assert entry["respiration_min"] == 9.1
        assert entry["respiration_max"] == 17.8
        assert entry["spo2_avg"] == 96.5
        assert entry["spo2_min"] == 92.0
        assert entry["skin_temperature_avg"] == 33.2
    assert state.database.training_status is None
    assert cache_cleared is True


def test_sync_garmin_data_calls_athlete_profile_sync_before_resolving_activity_tss(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Issue #102: sync_garmin_data must refresh the Intervals.icu athlete
    profile before it resolves any activity's TSS this run, so a freshly
    synced FTP applies immediately rather than only on the next sync."""
    state = _StubState(_StubDatabase(_make_database(tmp_path)))
    monkeypatch.setattr(sync_service, "clear_data_caches", lambda: None)

    call_order: list[str] = []

    def fake_sync_athlete_profile(database):
        call_order.append("profile_sync")
        return {"synced": True, "reason": None, "profile": {}}

    original_sync_activities = sync_service._sync_activities

    def wrapped_sync_activities(database, activities, **kwargs):
        call_order.append("activities")
        return original_sync_activities(database, activities, **kwargs)

    monkeypatch.setattr(sync_service.intervals_icu_service, "sync_athlete_profile", fake_sync_athlete_profile)
    monkeypatch.setattr(sync_service, "_sync_activities", wrapped_sync_activities)

    sync_service.sync_garmin_data(state, days=1, on_progress=None)

    assert call_order == ["profile_sync", "activities"]


def test_sync_garmin_data_folds_athlete_profile_failure_into_warnings(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """A real Intervals.icu failure (not just "not configured") must show up
    as a warning, not silently disappear or abort the Garmin sync."""
    state = _StubState(_StubDatabase(_make_database(tmp_path)))
    monkeypatch.setattr(sync_service, "clear_data_caches", lambda: None)
    monkeypatch.setattr(
        sync_service.intervals_icu_service,
        "sync_athlete_profile",
        lambda database: {"synced": False, "reason": "Не удалось подключиться к Intervals.icu: timeout", "profile": None},
    )

    result = sync_service.sync_garmin_data(state, days=1, on_progress=None)

    assert any("Intervals.icu" in warning and "timeout" in warning for warning in result.warnings)


def test_sync_status_payload_summarizes_fresh_training_data():
    result = sync_service.GarminSyncResult(
        activity_result={"new": 2, "updated": 1, "skipped": 0},
        hrv_result={"new": 3, "updated": 0},
        sleep_result={"new": 2, "updated": 0},
        health_result={"new": 2, "updated": 0},
        training_status_result={"new": 1, "updated": 0},
        success_messages=[
            "🆕 2 новых активностей",
            "🔄 1 активность обновлена",
            "💓 3 новых HRV записей",
        ],
        details=["🎯 Статус тренированности обновлён"],
    )

    payload = sync_service.build_sync_status_payload(result, days=30)

    assert payload["severity"] == "success"
    assert "Синхронизация Garmin завершена" == payload["title"]
    assert payload["activity_changes"] == 3
    assert payload["recovery_changes"] == 8
    assert payload["highlights"][:2] == [
        "🆕 2 новых активностей",
        "🔄 1 активность обновлена",
    ]


def test_sync_status_payload_marks_partial_when_warnings_exist():
    result = sync_service.GarminSyncResult(
        activity_result={"new": 2, "updated": 0, "skipped": 0},
        warnings=["⚠️ Garmin sleep 2026-01-02: 429 Too Many Requests"],
        success_messages=["🆕 2 новых активностей"],
    )

    payload = sync_service.build_sync_status_payload(result, days=30)

    assert payload["severity"] == "warning"
    assert payload["title"] == "Синхронизация Garmin завершена частично"
    assert payload["activity_changes"] == 2
    assert payload["notices"][0].startswith("⚠️ Garmin sleep")


def test_peak_body_battery_uses_the_days_peak_not_the_last_reading():
    # Real incident: same date read as 80.0 the morning it happened, then
    # 16.0 the next day once the full day's array was available.
    battery_values = [
        [1767250800000, 42],
        [1767261600000, 80],
        [1767296400000, 61],
        [1767322800000, 16],
    ]

    assert sync_service._peak_body_battery(battery_values) == 80


def test_peak_body_battery_handles_monotonic_increasing_day():
    battery_values = [[0, 30], [1, 55], [2, 90]]

    assert sync_service._peak_body_battery(battery_values) == 90


def test_peak_body_battery_ignores_null_points():
    battery_values = [[0, None], [1, 45], [2, None]]

    assert sync_service._peak_body_battery(battery_values) == 45


def test_peak_body_battery_empty_array_returns_none():
    assert sync_service._peak_body_battery([]) is None
    assert sync_service._peak_body_battery([[0, None]]) is None


def test_sync_service_retries_transient_sleep_errors(monkeypatch: pytest.MonkeyPatch, tmp_path):
    state = _FlakySleepState(_StubDatabase(_make_database(tmp_path)))
    monkeypatch.setattr(sync_service, "clear_data_caches", lambda: None)
    monkeypatch.setattr(sync_service.time, "sleep", lambda _seconds: None)

    result = sync_service.sync_garmin_data(state, days=1, on_progress=None)

    assert state.garmin_client.sleep_calls >= 2
    assert result.sleep_result["new"] >= 1
    assert not any("Garmin sleep" in warning for warning in result.warnings)


class _RespirationNotFoundClient(_StubGarminClient):
    """Issue #90: аккаунт/устройство без respiration отдаёт постоянную (не
    transient) ошибку на каждый вызов."""

    def __init__(self) -> None:
        super().__init__()
        self.respiration_calls = 0

    def get_respiration_data(self, _date):
        self.respiration_calls += 1
        self._last_error = {
            "context": "respiration",
            "message": "404 Client Error: Not Found for endpoint /wellness-service/wellness/dailyRespiration",
        }
        return None


def test_collect_phase1_daily_data_stops_calling_unsupported_signal_after_first_failure() -> None:
    """Issue #90: после первой не-transient ошибки сигнал не должен опрашиваться
    повторно на каждую следующую дату прогона (устраняет retry-шторм)."""
    client = _RespirationNotFoundClient()
    dates = [datetime(2026, 7, 1) + timedelta(days=i) for i in range(5)]

    _sleep_data, _health_data, warnings = sync_service._collect_phase1_daily_data(client, dates)

    assert client.respiration_calls == 1
    respiration_warnings = [w for w in warnings if "respiration" in w]
    assert len(respiration_warnings) == 1
    assert "5 дн." in respiration_warnings[0]


def test_collect_phase1_daily_data_still_stores_other_signals_when_one_is_unsupported() -> None:
    client = _RespirationNotFoundClient()
    dates = [datetime(2026, 7, 1) + timedelta(days=i) for i in range(3)]

    _sleep_data, health_data, _warnings = sync_service._collect_phase1_daily_data(client, dates)

    assert len(health_data) == 3
    for entry in health_data.values():
        assert "respiration_avg" not in entry
        assert entry["spo2_avg"] == pytest.approx(96.5)

"""Issue #562 M1: provider-neutral capture contract and its five verdicts.

The wrapper under test is `services.recovery_analytics.capture_post_sync_recovery_state`.
It must describe the revision it just saved — not the day as a whole — and must
never let a derived-analytics failure escape into the caller.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging

import pytest

from config.settings import Settings
from data.database import Database
from models.recovery_response import select_daily_anchor

DAY = "2026-07-16"
MOSCOW_OBSERVED = datetime(2026, 7, 16, 5, 0, tzinfo=timezone.utc)  # 08:00 локально
LOCAL_NOON_UTC = datetime(2026, 7, 16, 9, 0, tzinfo=timezone.utc)  # 12:00 Europe/Moscow

pytestmark = pytest.mark.smoke


@pytest.fixture(autouse=True)
def _moscow(monkeypatch):
    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow")


def _seed_full_day(db: Database, day: str = DAY) -> None:
    """Полный набор измерений за день: снапшот проходит eligibility gate."""
    db.sync_sleep_data(
        {day: {"total_sleep_minutes": 480, "sleep_score": 82.0, "sleep_score_observed_at": day,
               "total_sleep_observed_at": day}}
    )
    db.sync_hrv_data({day: {"rmssd": 45.0, "stress_score": 20.0, "rmssd_observed_at": day}})
    db.sync_daily_health({day: {"resting_hr": 52, "resting_hr_observed_at": day}})
    db.sync_training_status(
        {day: {"training_status": "PRODUCTIVE", "training_readiness": 78.0,
               "training_readiness_observed_at": day}}
    )


def _seed_partial_day(db: Database, day: str = DAY) -> None:
    """Только сон: confidence ниже порога → снимок непригоден.

    Даже если рядом появится активность (фактор TSB), 2 из 5 факторов дают
    0.4 < 0.60, поэтому снимок остаётся непригодным и проверяемый предикат
    не маскируется пригодностью.
    """
    db.sync_sleep_data({day: {"total_sleep_minutes": 480, "sleep_score": 82.0}})


def _save_activity(db: Database, *, started_at_utc: str | None, day: str = DAY,
                   activity_id: str = "ride-1") -> None:
    db.save_activities(
        [
            {
                "activity_id": activity_id,
                "date": day,
                "started_at_utc": started_at_utc,
                "sport": "bike",
                "duration_minutes": 60,
                "tss": 60.0,
            }
        ]
    )


def _capture(db: Database, *, run_id: str, observed: datetime, provider: str = "garmin") -> dict:
    from services.recovery_analytics import capture_post_sync_recovery_state

    return capture_post_sync_recovery_state(
        db, capture_run_id=run_id, provider=provider, observed_at_utc=observed
    )


def test_capture_before_load_when_no_activity_started(tmp_path):
    db = Database(str(tmp_path / "capture.db"))
    _seed_full_day(db)

    result = _capture(db, run_id="run-1", observed=MOSCOW_OBSERVED)
    block = result["recovery_capture"]

    assert block["status"] == "saved_before_load"
    assert block["reason"] is None
    assert block["eligibility_status"] == "eligible"
    assert block["provider"] == "garmin"
    assert block["capture_run_id"] == "run-1"
    assert block["local_date"] == DAY
    assert block["observed_at_utc"] == "2026-07-16T05:00:00Z"
    assert block["cutoff_at_utc"] == LOCAL_NOON_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert block["revision"] == 1
    assert block["created"] is True
    assert block["error"] is None


def test_capture_exposes_local_time_for_the_athlete(tmp_path):
    db = Database(str(tmp_path / "local.db"))
    _seed_full_day(db)

    block = _capture(db, run_id="run-local", observed=MOSCOW_OBSERVED)["recovery_capture"]

    assert block["observed_at_local"] == "2026-07-16T08:00:00+03:00"


def test_capture_too_late_when_activity_started_earlier(tmp_path):
    db = Database(str(tmp_path / "late.db"))
    _seed_full_day(db)
    _save_activity(db, started_at_utc="2026-07-16T06:00:00Z")  # 09:00 локально

    block = _capture(
        db, run_id="run-late", observed=datetime(2026, 7, 16, 7, 0, tzinfo=timezone.utc)
    )["recovery_capture"]

    assert block["status"] == "saved_too_late"
    assert block["cutoff_at_utc"] == "2026-07-16T06:00:00Z"
    # Снимок остаётся аудируемой записью дня.
    assert block["revision"] == 1
    assert block["created"] is True


def test_capture_too_late_after_local_noon_without_activities(tmp_path):
    db = Database(str(tmp_path / "noon.db"))
    _seed_full_day(db)

    block = _capture(
        db, run_id="run-noon", observed=datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
    )["recovery_capture"]

    assert block["status"] == "saved_too_late"
    assert block["cutoff_at_utc"] == "2026-07-16T09:00:00Z"


def test_capture_status_is_per_revision_not_per_day(tmp_path):
    """Ревизия 05:00 — до нагрузки, ревизия 11:00 после активности — слишком поздно."""
    db = Database(str(tmp_path / "revisions.db"))
    _seed_full_day(db)

    first = _capture(db, run_id="run-early", observed=MOSCOW_OBSERVED)["recovery_capture"]
    _save_activity(db, started_at_utc="2026-07-16T07:00:00Z")  # 10:00 локально
    second = _capture(
        db, run_id="run-late", observed=datetime(2026, 7, 16, 8, 0, tzinfo=timezone.utc)
    )["recovery_capture"]

    assert first["status"] == "saved_before_load"
    assert second["status"] == "saved_too_late"
    assert second["revision"] == 2
    # Дневной anchor остаётся у ранней ревизии — поздняя его не «украла».
    anchor = select_daily_anchor(
        db.get_readiness_snapshots(capture_mode="prospective", local_date=DAY),
        db.get_activities_between("2026-07-15", DAY),
        local_date=date.fromisoformat(DAY),
        athlete_timezone=Settings.ATHLETE_TIMEZONE,
    )
    assert anchor["reason"] is None
    assert anchor["snapshot"]["revision"] == 1
    assert anchor["snapshot"]["observed_at_utc"] == "2026-07-16T05:00:00Z"


def test_capture_activity_start_missing_wins_over_ineligible(tmp_path):
    """Пересечение предикатов: непригодный снимок + нечитаемый старт → activity_start_missing."""
    db = Database(str(tmp_path / "missing-start.db"))
    _seed_partial_day(db)
    _save_activity(db, started_at_utc=None)

    block = _capture(db, run_id="run-missing", observed=MOSCOW_OBSERVED)["recovery_capture"]

    assert block["status"] == "activity_start_missing"
    assert block["reason"] == "activity_start_missing"
    assert block["eligibility_status"] == "ineligible"  # факт остаётся видимым в блоке


def test_capture_ineligible_reports_safe_reasons(tmp_path):
    db = Database(str(tmp_path / "ineligible.db"))
    _seed_partial_day(db)

    block = _capture(db, run_id="run-ineligible", observed=MOSCOW_OBSERVED)["recovery_capture"]

    assert block["status"] == "ineligible"
    assert block["eligibility_status"] == "ineligible"
    assert "low_confidence" in block["eligibility_reasons"]
    assert block["reason"] == "low_confidence"
    # Причина машинно-читаемая и не содержит приватных значений снимка.
    assert str(block["reason"]).startswith("low_confidence")


def test_capture_on_empty_database_is_ineligible_not_a_crash(tmp_path):
    db = Database(str(tmp_path / "empty.db"))

    block = _capture(db, run_id="run-empty", observed=MOSCOW_OBSERVED)["recovery_capture"]

    assert block["status"] == "ineligible"
    assert "missing_score" in block["eligibility_reasons"]


def test_capture_failure_is_reported_not_raised(tmp_path, monkeypatch):
    """Ошибка derived capture не выходит наружу: данные синхронизации важнее."""
    from services import recovery_analytics

    db = Database(str(tmp_path / "failure.db"))
    _seed_full_day(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("derived analytics unavailable: /private/athlete.db")

    monkeypatch.setattr(recovery_analytics, "record_post_sync_recovery_state", _boom)

    result = recovery_analytics.capture_post_sync_recovery_state(
        db, capture_run_id="run-failed", provider="intervals", observed_at_utc=MOSCOW_OBSERVED
    )
    block = result["recovery_capture"]

    assert block["status"] == "capture_failed"
    assert block["error"] == "snapshot_capture_failed"
    assert block["reason"] == "snapshot_capture_failed"
    assert "athlete.db" not in str(block)
    assert block["snapshot_id"] is None
    assert block["revision"] is None
    assert block["provider"] == "intervals"
    assert result["created"] is False


def test_capture_activity_lookup_failure_fails_closed_with_safe_reason(
    tmp_path, monkeypatch
):
    """A saved revision must not become a false pre-load success on read failure."""
    db = Database(str(tmp_path / "lookup-failure.db"))
    _seed_full_day(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("sqlite failure at /private/athlete.db")

    monkeypatch.setattr(db, "get_activities_between", _boom)

    result = _capture(db, run_id="run-lookup-failed", observed=MOSCOW_OBSERVED)
    block = result["recovery_capture"]

    assert result["created"] is True
    assert block["snapshot_id"] is not None
    assert block["revision"] == 1
    assert block["status"] == "capture_failed"
    assert block["reason"] == "activity_lookup_failed"
    assert block["error"] == "activity_lookup_failed"
    assert "athlete.db" not in str(block)


def test_capture_recorder_failure_logs_one_traceback_record(tmp_path, monkeypatch, caplog):
    """F3: сбой capture логируется серверно, публичный блок остаётся без сырого текста."""
    from services import recovery_analytics

    db = Database(str(tmp_path / "logged-failure.db"))
    _seed_full_day(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("sqlite failure at /private/athlete.db")

    monkeypatch.setattr(recovery_analytics, "record_post_sync_recovery_state", _boom)
    caplog.set_level(logging.WARNING, logger="services.recovery_analytics")

    result = recovery_analytics.capture_post_sync_recovery_state(
        db, capture_run_id="run-logged", provider="garmin", observed_at_utc=MOSCOW_OBSERVED
    )
    block = result["recovery_capture"]

    records = [
        record
        for record in caplog.records
        if record.name == "services.recovery_analytics" and record.levelno == logging.WARNING
    ]
    assert len(records) == 1, [record.getMessage() for record in records]
    assert records[0].exc_info is not None, "traceback обязателен для диагностики"
    message = records[0].getMessage()
    assert "snapshot_capture_failed" in message
    assert "athlete.db" not in message
    assert "athlete.db" not in str(block)
    assert block["status"] == "capture_failed"
    assert block["reason"] == "snapshot_capture_failed"


def test_activity_lookup_failure_logs_one_traceback_record(tmp_path, monkeypatch, caplog):
    """F3: второй fail-closed выход тоже оставляет серверный след ровно один раз."""
    db = Database(str(tmp_path / "logged-lookup.db"))
    _seed_full_day(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("sqlite failure at /private/athlete.db")

    monkeypatch.setattr(db, "get_activities_between", _boom)
    caplog.set_level(logging.WARNING, logger="services.recovery_analytics")

    result = _capture(db, run_id="run-lookup-logged", observed=MOSCOW_OBSERVED)
    block = result["recovery_capture"]

    records = [
        record
        for record in caplog.records
        if record.name == "services.recovery_analytics" and record.levelno == logging.WARNING
    ]
    assert len(records) == 1, [record.getMessage() for record in records]
    assert records[0].exc_info is not None
    assert "activity_lookup_failed" in records[0].getMessage()
    assert "athlete.db" not in records[0].getMessage()
    assert "athlete.db" not in str(block)
    assert block["status"] == "capture_failed"
    assert block["reason"] == "activity_lookup_failed"


def test_capture_provider_is_persisted_in_provenance(tmp_path):
    """Провайдер дурабелен: он пишется в существующий JSON провенансы журнала."""
    db = Database(str(tmp_path / "provider.db"))
    _seed_full_day(db)

    _capture(db, run_id="run-provider", observed=MOSCOW_OBSERVED, provider="intervals")

    rows = db.get_readiness_snapshots(capture_mode="prospective", local_date=DAY)
    assert len(rows) == 1
    assert rows[0]["provenance"]["capture_provider"] == "intervals"
    assert rows[0]["snapshot"]["input_provenance"]["capture_provider"] == "intervals"


def test_capture_run_identity_is_idempotent(tmp_path):
    db = Database(str(tmp_path / "identity.db"))
    _seed_full_day(db)

    first = _capture(db, run_id="run-same", observed=MOSCOW_OBSERVED)["recovery_capture"]
    retry = _capture(
        db, run_id="run-same", observed=datetime(2026, 7, 16, 6, 0, tzinfo=timezone.utc)
    )["recovery_capture"]
    other = _capture(
        db, run_id="run-other", observed=datetime(2026, 7, 16, 6, 30, tzinfo=timezone.utc)
    )["recovery_capture"]

    assert first["created"] is True
    assert retry["created"] is False
    assert retry["snapshot_id"] == first["snapshot_id"]
    assert retry["revision"] == 1
    assert other["created"] is True
    assert other["revision"] == 2
    assert len(db.get_readiness_snapshots(capture_mode="prospective", local_date=DAY)) == 2


def test_capture_status_matches_the_daily_anchor_decision(tmp_path):
    """Дневной инвариант: anchor существует ⇔ есть ревизия со статусом before_load."""
    db = Database(str(tmp_path / "anchor.db"))
    _seed_full_day(db)

    before = _capture(db, run_id="run-1", observed=MOSCOW_OBSERVED)["recovery_capture"]
    activities = db.get_activities_between("2026-07-15", DAY)
    found = select_daily_anchor(
        db.get_readiness_snapshots(capture_mode="prospective", local_date=DAY),
        activities,
        local_date=date.fromisoformat(DAY),
        athlete_timezone=Settings.ATHLETE_TIMEZONE,
    )

    assert before["status"] == "saved_before_load"
    assert found["reason"] is None
    assert found["snapshot"]["capture_run_id"] == "run-1"

    # Тот же день, но снимок приходит только после старта активности → anchor'а нет.
    late_db = Database(str(tmp_path / "anchor-late.db"))
    _seed_full_day(late_db)
    _save_activity(late_db, started_at_utc="2026-07-16T04:00:00Z")
    late = _capture(
        late_db, run_id="run-late", observed=datetime(2026, 7, 16, 4, 30, tzinfo=timezone.utc)
    )["recovery_capture"]
    missing = select_daily_anchor(
        late_db.get_readiness_snapshots(capture_mode="prospective", local_date=DAY),
        late_db.get_activities_between("2026-07-15", DAY),
        local_date=date.fromisoformat(DAY),
        athlete_timezone=Settings.ATHLETE_TIMEZONE,
    )

    assert late["status"] == "saved_too_late"
    assert missing["reason"] == "no_eligible_pre_anchor_snapshot"
    assert missing["snapshot"] is None


def test_capture_accepts_an_explicit_activity_window(tmp_path):
    """Окно активностей можно передать явно — контракт не требует чтения из БД."""
    from services.recovery_analytics import capture_post_sync_recovery_state

    db = Database(str(tmp_path / "explicit.db"))
    _seed_full_day(db)

    result = capture_post_sync_recovery_state(
        db,
        capture_run_id="run-explicit",
        provider="garmin",
        observed_at_utc=datetime(2026, 7, 16, 7, 0, tzinfo=timezone.utc),
        activities=[
            {"date": DAY, "started_at_utc": "2026-07-16T06:00:00Z"},
            {"date": (date.fromisoformat(DAY) - timedelta(days=1)).isoformat(),
             "started_at_utc": "2026-07-15T06:00:00Z"},
        ],
    )

    block = result["recovery_capture"]
    assert block["status"] == "saved_too_late"
    assert block["cutoff_at_utc"] == "2026-07-16T06:00:00Z"

"""Issue #557 M3 slice 3.2: RHR observation provenance.

The stored `daily_health.date` is the requested sync date, so it cannot prove
*when* the resting heart rate was measured. Provenance comes from the provider:
a Garmin measurement timestamp (converted to the athlete timezone) or the
Intervals.icu wellness `id` (already provider-local). It must move only
together with the metric that was actually accepted.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from data.data_processor_phase1 import Phase1DataProcessor
from data.database import Database


def _date_of(day: str = "2026-07-16"):
    return date.fromisoformat(day)


def _health_row(db: Database, day: str = "2026-07-16"):
    return db.get_daily_health(days=36500).set_index("date").loc[day]


# --------------------------------------------------------------- Garmin client


def test_rhr_observed_at_converts_utc_timestamp_to_athlete_local(monkeypatch):
    from config.settings import Settings

    from data.garmin_client import GarminClient

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow", raising=False)

    normalized = GarminClient._normalize_rhr_payload(
        {"restingHeartRate": 52, "startTimeGMT": "2026-07-15T22:30:00.0"}
    )

    assert normalized["restingHeartRate"] == 52
    # 22:30Z is already the next calendar day for a Moscow athlete.
    assert normalized["observedAt"] == "2026-07-16"


def test_rhr_observed_at_keeps_local_calendar_date_without_conversion(monkeypatch):
    from config.settings import Settings

    from data.garmin_client import GarminClient

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow", raising=False)

    normalized = GarminClient._normalize_rhr_payload(
        {"restingHeartRate": 52, "calendarDate": "2026-07-16"}
    )

    assert normalized["observedAt"] == "2026-07-16"


def test_rhr_observed_at_reads_the_metrics_map_entry():
    from data.garmin_client import GarminClient

    normalized = GarminClient._normalize_rhr_payload(
        {
            "allMetrics": {
                "metricsMap": {
                    "WELLNESS_RESTING_HEART_RATE": [
                        {"value": 48, "calendarDate": "2026-07-16"}
                    ]
                }
            }
        }
    )

    assert normalized == {"restingHeartRate": 48, "observedAt": "2026-07-16"}


def test_rhr_observed_at_is_none_without_a_provider_date():
    from data.garmin_client import GarminClient

    assert GarminClient._normalize_rhr_payload({"restingHeartRate": 52})["observedAt"] is None
    assert (
        GarminClient._normalize_rhr_payload(
            {"restingHeartRate": 52, "calendarDate": "not-a-date"}
        )["observedAt"]
        is None
    )


# ------------------------------------------------------------------ processor


def test_processor_carries_rhr_observation_date():
    processed = Phase1DataProcessor.process_daily_health_data(
        None, {"restingHeartRate": 52, "observedAt": "2026-07-16"}
    )
    assert processed is not None
    assert processed["resting_hr"] == 52
    assert processed["resting_hr_observed_at"] == "2026-07-16"

    dateless = Phase1DataProcessor.process_daily_health_data(
        None, {"restingHeartRate": 52}
    )
    assert dateless is not None
    assert dateless["resting_hr_observed_at"] is None


# ---------------------------------------------------------------- persistence


def test_rhr_provenance_round_trips_and_survives_a_dateless_resync(tmp_path):
    db = Database(str(tmp_path / "rhr_round_trip.db"))
    db.sync_daily_health(
        {"2026-07-16": {"resting_hr": 52, "resting_hr_source": "garmin",
                        "resting_hr_observed_at": "2026-07-16"}}
    )
    # Legacy/undated row -> NULL, never the query date.
    db.sync_daily_health({"2026-07-17": {"resting_hr": 60, "resting_hr_source": "garmin"}})

    rows = db.get_daily_health(days=36500).set_index("date")
    assert rows.loc["2026-07-16", "resting_hr_observed_at"] == "2026-07-16"
    assert pd.isna(rows.loc["2026-07-17", "resting_hr_observed_at"])

    # A dateless re-sync must not erase the known observation date.
    db.sync_daily_health({"2026-07-16": {"resting_hr": 52, "resting_hr_source": "garmin"}})
    kept = db.get_daily_health(days=36500).set_index("date")
    assert kept.loc["2026-07-16", "resting_hr_observed_at"] == "2026-07-16"


def test_changed_undated_rhr_clears_inherited_provenance(tmp_path, monkeypatch):
    """Review P1 audit: the same rule applies to the RHR writer."""
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "rhr_inherit.db"))
    db.sync_daily_health(
        {"2026-07-16": {"resting_hr": 52, "resting_hr_source": "garmin",
                        "resting_hr_observed_at": "2026-07-15"}}
    )

    db.sync_daily_health({"2026-07-16": {"resting_hr": 60, "resting_hr_source": "garmin"}})
    changed = _health_row(db)
    assert changed["resting_hr"] == 60
    assert pd.isna(changed["resting_hr_observed_at"])

    # Unchanged value without a date keeps the known provenance.
    db.sync_daily_health(
        {"2026-07-16": {"resting_hr": 60, "resting_hr_source": "garmin",
                        "resting_hr_observed_at": "2026-07-15"}}
    )
    db.sync_daily_health({"2026-07-16": {"resting_hr": 60, "resting_hr_source": "garmin"}})
    kept = _health_row(db)
    assert kept["resting_hr_observed_at"] == "2026-07-15"


def test_legacy_daily_health_table_migrates_and_exposes_null_provenance(tmp_path):
    db_path = tmp_path / "legacy_health.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE daily_health (
            date DATE PRIMARY KEY,
            resting_hr INTEGER,
            steps INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO daily_health (date, resting_hr, steps) VALUES ('2026-07-15', 55, 8000)"
    )
    conn.commit()
    conn.close()

    Database(str(db_path))

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(daily_health)")}
    row = conn.execute(
        "SELECT resting_hr, resting_hr_observed_at FROM daily_health WHERE date='2026-07-15'"
    ).fetchone()
    conn.close()

    assert "resting_hr_observed_at" in columns
    assert row == (55, None)


# ------------------------------------------------------- provider arbitration


def test_rejected_rhr_does_not_change_accepted_provenance(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "rhr_collision.db"))
    db.sync_daily_health(
        {"2026-07-16": {"resting_hr": 52, "resting_hr_source": "garmin",
                        "resting_hr_observed_at": "2026-07-15"}}
    )

    # Intervals offers another value for the same day; garmin stays primary.
    db.sync_daily_health(
        {"2026-07-16": {"resting_hr": 48, "resting_hr_source": "intervals",
                        "resting_hr_observed_at": "2026-07-16"}}
    )

    row = _health_row(db)
    assert row["resting_hr"] == 52
    assert row["resting_hr_source"] == "garmin"
    assert row["resting_hr_observed_at"] == "2026-07-15"


def test_accepted_rhr_updates_value_source_and_provenance_together(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "rhr_accept.db"))
    db.sync_daily_health(
        {"2026-07-16": {"resting_hr": 48, "resting_hr_source": "intervals",
                        "resting_hr_observed_at": "2026-07-16"}}
    )
    db.sync_daily_health(
        {"2026-07-16": {"resting_hr": 52, "resting_hr_source": "garmin",
                        "resting_hr_observed_at": "2026-07-15"}}
    )

    row = _health_row(db)
    assert row["resting_hr"] == 52
    assert row["resting_hr_source"] == "garmin"
    assert row["resting_hr_observed_at"] == "2026-07-15"


def test_intervals_wellness_batch_records_rhr_observation_date(tmp_path):
    from services.wellness_ingest import normalize_intervals_wellness

    db = Database(str(tmp_path / "rhr_intervals.db"))
    record = normalize_intervals_wellness({"id": "2026-07-16", "restingHR": 48})
    db.sync_wellness_batch(
        [record.as_payload()],
        provider="intervals",
        cursor_value="2026-07-16",
        primary_source="intervals",
        received_at="2026-07-16T06:00:00Z",
    )

    row = _health_row(db)
    assert row["resting_hr"] == 48
    assert row["resting_hr_source"] == "intervals"
    assert row["resting_hr_observed_at"] == "2026-07-16"


def test_intervals_wellness_rejected_rhr_keeps_existing_provenance(tmp_path, monkeypatch):
    from config.settings import Settings

    from services.wellness_ingest import normalize_intervals_wellness

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "rhr_intervals_rejected.db"))
    db.sync_daily_health(
        {"2026-07-16": {"resting_hr": 52, "resting_hr_source": "garmin",
                        "resting_hr_observed_at": "2026-07-15"}}
    )
    record = normalize_intervals_wellness({"id": "2026-07-16", "restingHR": 48})
    db.sync_wellness_batch(
        [record.as_payload()],
        provider="intervals",
        cursor_value="2026-07-16",
        primary_source="garmin",
        received_at="2026-07-16T06:00:00Z",
    )

    row = _health_row(db)
    assert row["resting_hr"] == 52
    assert row["resting_hr_source"] == "garmin"
    assert row["resting_hr_observed_at"] == "2026-07-15"


# ------------------------------------------------------------ eligibility/snapshot


def test_dated_rhr_is_confirmed_today_and_dateless_is_not(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "rhr_snapshot.db"))
    db.sync_daily_health(
        {"2026-07-16": {"resting_hr": 52, "resting_hr_source": "garmin",
                        "resting_hr_observed_at": "2026-07-16"}}
    )
    snapshot = build_readiness_snapshot(
        db,
        as_of=_date_of(),
        observed_at_utc=datetime(2026, 7, 16, 6, 0, tzinfo=timezone.utc),
    )

    assert snapshot["freshness"]["confirmed_today"] == ["resting_hr"]
    assert "resting_hr" in snapshot["eligible_inputs"]
    assert snapshot["freshness"]["state"] == "provisional"

    # The same value without a provider date stays unverified.
    dateless = Database(str(tmp_path / "rhr_dateless.db"))
    dateless.sync_daily_health(
        {"2026-07-16": {"resting_hr": 52, "resting_hr_source": "garmin"}}
    )
    undated_snapshot = build_readiness_snapshot(
        dateless,
        as_of=_date_of(),
        observed_at_utc=datetime(2026, 7, 16, 6, 0, tzinfo=timezone.utc),
    )
    assert undated_snapshot["freshness"]["confirmed_today"] == []
    assert undated_snapshot["freshness"]["unverified"] == ["resting_hr"]


# ------------------------------------------------------------------- helpers


def test_athlete_local_observation_requires_a_valid_timezone(monkeypatch):
    """Review P2: an unusable athlete timezone must fail closed for both sources."""
    from config.settings import Settings

    from utils.observation_provenance import observation_local_date

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "not/a-zone", raising=False)

    assert observation_local_date("2026-07-16", source="athlete_local") is None
    assert observation_local_date("2026-07-16T00:20:00Z", source="utc") is None

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow", raising=False)
    assert observation_local_date("2026-07-16", source="athlete_local") == date(2026, 7, 16)


def test_invalid_timezone_keeps_rhr_unverified_end_to_end(tmp_path, monkeypatch):
    from config.settings import Settings

    from api.readiness_snapshot import build_readiness_snapshot
    from data.garmin_client import GarminClient

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "not/a-zone", raising=False)

    normalized = GarminClient._normalize_rhr_payload(
        {"restingHeartRate": 52, "calendarDate": "2026-07-16"}
    )
    assert normalized["observedAt"] is None

    processed = Phase1DataProcessor.process_daily_health_data(None, normalized)
    assert processed is not None
    assert processed["resting_hr_observed_at"] is None

    db = Database(str(tmp_path / "invalid_tz.db"))
    db.sync_daily_health(
        {
            "2026-07-16": {
                "resting_hr": processed["resting_hr"],
                "resting_hr_source": "garmin",
                "resting_hr_observed_at": processed["resting_hr_observed_at"],
            }
        }
    )
    snapshot = build_readiness_snapshot(
        db,
        as_of=_date_of(),
        observed_at_utc=datetime(2026, 7, 16, 6, 0, tzinfo=timezone.utc),
    )

    assert snapshot["freshness"]["confirmed_today"] == []
    assert snapshot["freshness"]["unverified"] == ["resting_hr"]
    assert snapshot["eligible_inputs"] == []
    assert snapshot["intervention_score"] is None
    assert snapshot["intervention_blocked_reason"] == "no_intervention_eligible_factors"


def test_neutral_timezone_helper_matches_the_delivery_delegate():
    from services.intervals_plan_delivery import athlete_local_date as delegate
    from utils.athlete_time import athlete_local_date as canonical

    observed = datetime(2026, 7, 15, 22, 30, tzinfo=timezone.utc)
    assert canonical(observed) == delegate(observed)

    with pytest.raises(ValueError):
        canonical(datetime(2026, 7, 15, 22, 30))
    with pytest.raises(ValueError):
        delegate(datetime(2026, 7, 15, 22, 30))

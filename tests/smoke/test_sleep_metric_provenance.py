"""Contributor-safe contract tests for Garmin sleep metric provenance.

Fixtures reproduce the provider shape without credentials, network, or the
maintainer's SQLite database.
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd
import pytest

from data.data_processor_phase1 import Phase1DataProcessor
from data.database import Database


def _nested_garmin_payload() -> dict:
    return {
        "calendarDate": "2026-07-16",
        "dailySleepDTO": {
            "sleepTimeSeconds": 402 * 60,
            "deepSleepSeconds": 45 * 60,
            "lightSleepSeconds": 326 * 60,
            "remSleepSeconds": 32 * 60,
            "awakeSleepSeconds": 30 * 60,
            "awakeCount": 2,
            "sleepStartTimestampLocal": "2026-07-15T23:58:00",
            "sleepEndTimestampLocal": "2026-07-16T07:11:00",
            "sleepScores": {
                "overall": {"value": 62},
                "deepPercentage": {"value": 11},
                "lightPercentage": {"value": 81},
                "remPercentage": {"value": 8},
            },
        },
    }


def test_nested_garmin_score_and_awake_time_are_authoritative():
    result = Phase1DataProcessor.process_sleep_data(_nested_garmin_payload())

    assert result is not None
    assert result["sleep_score"] == 62
    assert result["sleep_score_source"] == "garmin"
    assert result["awake_sleep_minutes"] == 30
    assert result["sleep_efficiency"] == pytest.approx(93.1)
    assert result["sleep_efficiency_source"] == "derived_awake_time"
    assert result["total_sleep_minutes"] == 402
    assert result["deep_sleep_minutes"] == 45
    assert result["light_sleep_minutes"] == 326
    assert result["rem_sleep_minutes"] == 32


def test_legacy_top_level_garmin_score_remains_supported():
    payload = _nested_garmin_payload()
    payload["sleepScores"] = {"overall": {"value": 85}}
    payload["dailySleepDTO"].pop("sleepScores")

    result = Phase1DataProcessor.process_sleep_data(payload)

    assert result is not None
    assert result["sleep_score"] == 85
    assert result["sleep_score_source"] == "garmin"


def test_missing_garmin_score_is_explicitly_derived():
    payload = _nested_garmin_payload()
    payload["dailySleepDTO"].pop("sleepScores")
    payload["dailySleepDTO"].pop("awakeSleepSeconds")

    result = Phase1DataProcessor.process_sleep_data(payload)

    assert result is not None
    assert result["sleep_score"] == pytest.approx(47.7)
    assert result["sleep_score_source"] == "derived"
    assert result["awake_sleep_minutes"] is None
    assert result["sleep_efficiency"] == pytest.approx(92.8)
    assert result["sleep_efficiency_source"] == "derived_sleep_window"


def test_efficiency_is_unavailable_without_awake_time_or_sleep_window():
    payload = _nested_garmin_payload()
    payload["dailySleepDTO"].pop("awakeSleepSeconds")
    payload["dailySleepDTO"].pop("sleepStartTimestampLocal")
    payload["dailySleepDTO"].pop("sleepEndTimestampLocal")

    result = Phase1DataProcessor.process_sleep_data(payload)

    assert result is not None
    assert result["sleep_efficiency"] is None
    assert result["sleep_efficiency_source"] == "unavailable"


def test_legacy_sleep_table_migrates_without_rewriting_rows(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE sleep_data (
            date DATE PRIMARY KEY,
            total_sleep_minutes INTEGER,
            deep_sleep_minutes INTEGER,
            light_sleep_minutes INTEGER,
            rem_sleep_minutes INTEGER,
            awakenings_count INTEGER,
            sleep_score REAL,
            bedtime TEXT,
            wakeup_time TEXT,
            sleep_efficiency REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO sleep_data (
            date, total_sleep_minutes, sleep_score, sleep_efficiency
        ) VALUES ('2026-07-15', 420, 55.0, 90.0)
        """
    )
    conn.commit()
    conn.close()

    Database(str(db_path))

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sleep_data)")}
    row = conn.execute(
        """
        SELECT total_sleep_minutes, sleep_score, sleep_efficiency,
               awake_sleep_minutes, sleep_score_source, sleep_efficiency_source,
               sleep_score_observed_at, total_sleep_observed_at
        FROM sleep_data WHERE date = '2026-07-15'
        """
    ).fetchone()
    conn.close()

    # ASR-MOD-3: the migration adds the provenance columns and leaves legacy
    # rows untouched with NULL provenance (no invented observation date).
    assert {
        "awake_sleep_minutes",
        "sleep_score_source",
        "sleep_efficiency_source",
        "sleep_score_observed_at",
        "total_sleep_observed_at",
    } <= columns
    assert row == (
        420,
        55.0,
        90.0,
        None,
        "legacy_unknown",
        "legacy_unknown",
        None,
        None,
    )


def test_provenance_round_trips_through_database_and_sleep_api(tmp_path):
    from api.routers.sleep import sleep_summary

    db = Database(str(tmp_path / "sleep.db"))
    processed = Phase1DataProcessor.process_sleep_data(_nested_garmin_payload())
    assert processed is not None
    db.sync_sleep_data({"2026-07-16": processed})

    stored = db.get_sleep_data(days=10_000).iloc[0]
    assert stored["sleep_score_source"] == "garmin"
    assert stored["sleep_efficiency_source"] == "derived_awake_time"
    assert stored["awake_sleep_minutes"] == 30

    out = sleep_summary(days=10_000, db=db)
    assert out["latest"]["score"] == 62
    assert out["latest"]["score_source"] == "garmin"
    assert out["latest"]["efficiency_source"] == "derived_awake_time"
    assert out["latest"]["awake_minutes"] == 30
    assert out["trend"][-1]["score_source"] == "garmin"
    assert out["averages"]["score_source"] == "garmin"


def test_readiness_and_signal_do_not_call_derived_score_garmin():
    from models.readiness import _sleep_factor
    from models.signals_engine import _sleep_signal

    sleep_df = pd.DataFrame(
        [
            {
                "date": "2026-07-16",
                "total_sleep_minutes": 402,
                "sleep_score": 47.7,
                "sleep_score_source": "derived",
            }
        ]
    )

    factor = _sleep_factor(sleep_df, date(2026, 7, 16), max_age=2)
    signal = _sleep_signal(sleep_df)

    assert factor is not None
    assert "Garmin" not in factor["evidence"]
    assert "расчёт" in factor["evidence"].lower()
    assert factor["metric_source"] == "derived"
    assert signal["score_source"] == "derived"


# ---------------------------------------------------------------------------
# Issue #557 M3: sleep observation provenance. The stored row date is the query
# date when the payload carries no date, so it can never prove *when* the sleep
# was measured: only an explicitly parsed payload date may become
# `sleep_score_observed_at` / `total_sleep_observed_at`.
# ---------------------------------------------------------------------------


def test_sleep_observation_date_uses_calendar_date_without_timestamps():
    payload = _nested_garmin_payload()
    payload["dailySleepDTO"].pop("sleepStartTimestampLocal")
    payload["dailySleepDTO"].pop("sleepEndTimestampLocal")

    result = Phase1DataProcessor.process_sleep_data(payload)

    assert result is not None
    # The pair of local timestamps is absent, so the processor never sets
    # `sleep_date`; the payload calendar date is still a real observation date.
    assert result.get("sleep_date") is None
    assert result["sleep_score_observed_at"] == "2026-07-16"
    assert result["total_sleep_observed_at"] == "2026-07-16"


def test_sleep_observation_date_uses_wake_date_when_timestamps_exist():
    result = Phase1DataProcessor.process_sleep_data(_nested_garmin_payload())

    assert result is not None
    assert result["sleep_date"] == "2026-07-16"
    assert result["sleep_score_observed_at"] == "2026-07-16"
    assert result["total_sleep_observed_at"] == "2026-07-16"


def test_sleep_observation_date_is_none_without_any_payload_date():
    payload = _nested_garmin_payload()
    payload.pop("calendarDate")
    payload["dailySleepDTO"].pop("sleepStartTimestampLocal")
    payload["dailySleepDTO"].pop("sleepEndTimestampLocal")

    result = Phase1DataProcessor.process_sleep_data(payload)

    assert result is not None
    assert result["sleep_score_observed_at"] is None
    assert result["total_sleep_observed_at"] is None


def test_sleep_observation_date_is_none_for_invalid_calendar_date():
    payload = _nested_garmin_payload()
    payload["calendarDate"] = "not-a-date"
    payload["dailySleepDTO"].pop("sleepStartTimestampLocal")
    payload["dailySleepDTO"].pop("sleepEndTimestampLocal")

    result = Phase1DataProcessor.process_sleep_data(payload)

    assert result is not None
    assert result["sleep_score_observed_at"] is None
    assert result["total_sleep_observed_at"] is None


def test_sleep_observation_date_falls_back_to_the_dto_calendar_date():
    """Review P2: the captured real Garmin payload keeps calendarDate in the DTO."""
    payload = {
        "dailySleepDTO": {
            "id": 1755032275000,
            "calendarDate": "2025-08-13",
            "sleepTimeSeconds": 26100,
            "deepSleepSeconds": 3360,
            "lightSleepSeconds": 17520,
            "remSleepSeconds": 5220,
            "awakeSleepSeconds": 420,
            "awakeCount": 1,
        },
        "sleepScores": {"overall": {"value": 82, "qualifierKey": "GOOD"}},
    }

    result = Phase1DataProcessor.process_sleep_data(payload)

    assert result is not None
    assert result["sleep_score"] == 82
    assert result["sleep_score_observed_at"] == "2025-08-13"
    assert result["total_sleep_observed_at"] == "2025-08-13"


def test_sleep_provenance_round_trips_and_stays_null_for_legacy_rows(tmp_path):
    db = Database(str(tmp_path / "sleep_provenance.db"))

    # Row whose payload date is known -> provenance stored per metric.
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "total_sleep_minutes": 402,
                "total_sleep_source": "garmin",
                "total_sleep_observed_at": "2026-07-16",
                "sleep_score": 62.0,
                "sleep_score_source": "garmin",
                "sleep_score_observed_at": "2026-07-16",
            }
        }
    )
    # Legacy/undated row -> columns stay NULL, never the query date.
    db.sync_sleep_data({"2026-07-17": {"total_sleep_minutes": 400, "sleep_score": 60.0}})

    rows = db.get_sleep_data(days=36500).set_index("date")
    assert rows.loc["2026-07-16", "sleep_score_observed_at"] == "2026-07-16"
    assert rows.loc["2026-07-16", "total_sleep_observed_at"] == "2026-07-16"
    assert pd.isna(rows.loc["2026-07-17", "sleep_score_observed_at"])
    assert pd.isna(rows.loc["2026-07-17", "total_sleep_observed_at"])

    # A re-sync that learns the observation date updates the row...
    db.sync_sleep_data(
        {
            "2026-07-17": {
                "total_sleep_minutes": 400,
                "total_sleep_source": "garmin",
                "total_sleep_observed_at": "2026-07-16",
                "sleep_score": 60.0,
                "sleep_score_source": "garmin",
                "sleep_score_observed_at": "2026-07-16",
            }
        }
    )
    refreshed = db.get_sleep_data(days=36500).set_index("date")
    assert refreshed.loc["2026-07-17", "sleep_score_observed_at"] == "2026-07-16"
    assert refreshed.loc["2026-07-17", "total_sleep_observed_at"] == "2026-07-16"

    # ...while a later dateless re-sync must not erase it.
    db.sync_sleep_data(
        {"2026-07-17": {"total_sleep_minutes": 400, "sleep_score": 60.0}}
    )
    kept = db.get_sleep_data(days=36500).set_index("date")
    assert kept.loc["2026-07-17", "sleep_score_observed_at"] == "2026-07-16"
    assert kept.loc["2026-07-17", "total_sleep_observed_at"] == "2026-07-16"


def test_changed_undated_sleep_metrics_clear_inherited_provenance(tmp_path, monkeypatch):
    """Review P1 audit: score and duration must not inherit a stale date."""
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "sleep_inherit.db"))
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "total_sleep_minutes": 400.0,
                "total_sleep_source": "garmin",
                "total_sleep_observed_at": "2026-07-15",
                "sleep_score": 40.0,
                "sleep_score_source": "garmin",
                "sleep_score_observed_at": "2026-07-15",
            }
        }
    )

    # A new, undated value replaces both metrics.
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "total_sleep_minutes": 450.0,
                "total_sleep_source": "garmin",
                "sleep_score": 70.0,
                "sleep_score_source": "garmin",
            }
        }
    )
    changed = _sleep_row(db, "2026-07-16")
    assert changed["total_sleep_minutes"] == 450.0
    assert changed["sleep_score"] == 70.0
    assert pd.isna(changed["total_sleep_observed_at"])
    assert pd.isna(changed["sleep_score_observed_at"])

    # Unchanged undated re-syncs keep the known dates.
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "total_sleep_minutes": 450.0,
                "total_sleep_source": "garmin",
                "total_sleep_observed_at": "2026-07-15",
                "sleep_score": 70.0,
                "sleep_score_source": "garmin",
                "sleep_score_observed_at": "2026-07-15",
            }
        }
    )
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "total_sleep_minutes": 450.0,
                "total_sleep_source": "garmin",
                "sleep_score": 70.0,
                "sleep_score_source": "garmin",
            }
        }
    )
    kept = _sleep_row(db, "2026-07-16")
    assert kept["total_sleep_observed_at"] == "2026-07-15"
    assert kept["sleep_score_observed_at"] == "2026-07-15"


def _sleep_row(db: Database, day: str):
    return db.get_sleep_data(days=36500).set_index("date").loc[day]


def test_rejected_provider_metric_does_not_change_accepted_provenance(tmp_path, monkeypatch):
    """Issue #557 review P1: provenance must move only with the accepted metric."""
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "collision.db"))
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "total_sleep_minutes": 400.0,
                "total_sleep_source": "garmin",
                "total_sleep_observed_at": "2026-07-15",
                "sleep_score": 40.0,
                "sleep_score_source": "garmin",
                "sleep_score_observed_at": "2026-07-15",
            }
        }
    )

    # Intervals brings a friendlier score for the same day; garmin is primary,
    # so the value is rejected and its provenance must not be adopted either.
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "sleep_score": 90.0,
                "sleep_score_source": "intervals",
                "sleep_score_observed_at": "2026-07-16",
            }
        }
    )

    row = _sleep_row(db, "2026-07-16")
    assert row["sleep_score"] == 40.0
    assert row["sleep_score_source"] == "garmin"
    assert row["sleep_score_observed_at"] == "2026-07-15"


def test_accepted_metric_updates_value_source_and_provenance_atomically(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "accept.db"))
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "sleep_score": 90.0,
                "sleep_score_source": "intervals",
                "sleep_score_observed_at": "2026-07-16",
            }
        }
    )

    db.sync_sleep_data(
        {
            "2026-07-16": {
                "sleep_score": 50.0,
                "sleep_score_source": "garmin",
                "sleep_score_observed_at": "2026-07-15",
            }
        }
    )

    row = _sleep_row(db, "2026-07-16")
    assert row["sleep_score"] == 50.0
    assert row["sleep_score_source"] == "garmin"
    assert row["sleep_score_observed_at"] == "2026-07-15"


def test_derived_sleep_score_keeps_payload_provenance(tmp_path):
    """Review P2: the derived score comes from the same payload and must be dated."""
    payload = _nested_garmin_payload()
    payload["dailySleepDTO"].pop("sleepScores")

    processed = Phase1DataProcessor.process_sleep_data(payload)

    assert processed is not None
    assert processed["sleep_score_source"] == "derived"
    assert processed["sleep_score_observed_at"] == "2026-07-16"
    assert processed["total_sleep_observed_at"] == "2026-07-16"

    db = Database(str(tmp_path / "derived_score.db"))
    db.sync_sleep_data({"2026-07-16": processed})

    from models.readiness import OBSERVATION_CONFIRMED_TODAY, _sleep_factor

    factor = _sleep_factor(db.get_sleep_data(days=36500), date(2026, 7, 16), max_age=2)
    assert factor is not None
    assert factor["source"] == "sleep_score"
    assert factor["metric_source"] == "derived"
    assert factor["observation_as_of"] == "2026-07-16"
    assert factor["observation_status"] == OBSERVATION_CONFIRMED_TODAY
    assert factor["intervention_eligible"] is True


def test_derived_sleep_score_without_payload_date_is_unverified(tmp_path):
    payload = _nested_garmin_payload()
    payload.pop("calendarDate")
    payload["dailySleepDTO"].pop("sleepScores")
    payload["dailySleepDTO"].pop("sleepStartTimestampLocal")
    payload["dailySleepDTO"].pop("sleepEndTimestampLocal")

    processed = Phase1DataProcessor.process_sleep_data(payload)

    assert processed is not None
    assert processed["sleep_score_source"] == "derived"
    assert processed["sleep_score_observed_at"] is None

    db = Database(str(tmp_path / "dateless_derived.db"))
    db.sync_sleep_data({"2026-07-16": processed})

    from models.readiness import OBSERVATION_UNVERIFIED, _sleep_factor

    factor = _sleep_factor(db.get_sleep_data(days=36500), date(2026, 7, 16), max_age=2)
    assert factor is not None
    assert factor["observation_status"] == OBSERVATION_UNVERIFIED
    assert factor["intervention_eligible"] is False


def test_derived_sleep_score_reaches_the_snapshot_as_confirmed(tmp_path):
    from datetime import datetime, timezone

    from api.readiness_snapshot import build_readiness_snapshot

    payload = _nested_garmin_payload()
    payload["dailySleepDTO"].pop("sleepScores")
    processed = Phase1DataProcessor.process_sleep_data(payload)

    db = Database(str(tmp_path / "derived_snapshot.db"))
    db.sync_sleep_data({"2026-07-16": processed})

    snapshot = build_readiness_snapshot(
        db,
        as_of=date(2026, 7, 16),
        observed_at_utc=datetime(2026, 7, 16, 6, 0, tzinfo=timezone.utc),
    )

    assert snapshot["freshness"]["confirmed_today"] == ["sleep"]
    assert "sleep" not in snapshot["freshness"]["unverified"]
    assert snapshot["eligible_inputs"] == ["sleep"]
    assert snapshot["intervention_confidence"] == 0.2
    assert snapshot["intervention_score"] is not None
    assert snapshot["intervention_blocked_reason"] is None


def test_score_and_duration_provenance_stay_independent(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "scoped.db"))
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "total_sleep_minutes": 400.0,
                "total_sleep_source": "garmin",
                "total_sleep_observed_at": "2026-07-14",
                "sleep_score": 40.0,
                "sleep_score_source": "garmin",
                "sleep_score_observed_at": "2026-07-15",
            }
        }
    )

    # A duration-only update moves the duration provenance only.
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "total_sleep_minutes": 410.0,
                "total_sleep_source": "garmin",
                "total_sleep_observed_at": "2026-07-16",
            }
        }
    )

    row = _sleep_row(db, "2026-07-16")
    assert row["total_sleep_observed_at"] == "2026-07-16"
    assert row["sleep_score_observed_at"] == "2026-07-15"
    assert row["sleep_score"] == 40.0

    # `_sleep_factor` prefers the score, so it must report the score provenance.
    from models.readiness import OBSERVATION_CONFIRMED_TODAY, _sleep_factor

    frame = pd.DataFrame([dict(row, date="2026-07-16")])
    factor = _sleep_factor(frame, date(2026, 7, 16), max_age=2)
    assert factor is not None
    assert factor["source"] == "sleep_score"
    assert factor["observation_as_of"] == "2026-07-15"
    assert factor["observation_status"] != OBSERVATION_CONFIRMED_TODAY
    assert factor["intervention_eligible"] is False


def test_intervals_wellness_batch_persists_provider_local_observation_date(tmp_path):
    from models.readiness import OBSERVATION_CONFIRMED_TODAY, _sleep_factor
    from services.wellness_ingest import normalize_intervals_wellness

    db = Database(str(tmp_path / "intervals_sleep.db"))
    record = normalize_intervals_wellness(
        {"id": "2026-07-16", "sleepSecs": 400 * 60, "sleepScore": 80}
    )
    db.sync_wellness_batch(
        [record.as_payload()],
        provider="intervals",
        cursor_value="2026-07-16",
        primary_source="intervals",
        received_at="2026-07-16T06:00:00Z",
    )

    row = _sleep_row(db, "2026-07-16")
    assert row["total_sleep_observed_at"] == "2026-07-16"
    assert row["sleep_score_observed_at"] == "2026-07-16"

    factor = _sleep_factor(
        db.get_sleep_data(days=36500), date(2026, 7, 16), max_age=2
    )
    assert factor is not None
    assert factor["observation_status"] == OBSERVATION_CONFIRMED_TODAY
    assert factor["intervention_eligible"] is True


def test_intervals_wellness_rejected_update_keeps_existing_provenance(tmp_path, monkeypatch):
    from config.settings import Settings
    from services.wellness_ingest import normalize_intervals_wellness

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "intervals_rejected.db"))
    db.sync_sleep_data(
        {
            "2026-07-16": {
                "total_sleep_minutes": 400.0,
                "total_sleep_source": "garmin",
                "total_sleep_observed_at": "2026-07-15",
                "sleep_score": 40.0,
                "sleep_score_source": "garmin",
                "sleep_score_observed_at": "2026-07-15",
            }
        }
    )
    record = normalize_intervals_wellness(
        {"id": "2026-07-16", "sleepSecs": 400 * 60, "sleepScore": 90}
    )
    db.sync_wellness_batch(
        [record.as_payload()],
        provider="intervals",
        cursor_value="2026-07-16",
        primary_source="garmin",
        received_at="2026-07-16T06:00:00Z",
    )

    row = _sleep_row(db, "2026-07-16")
    assert row["sleep_score"] == 40.0
    assert row["sleep_score_source"] == "garmin"
    assert row["sleep_score_observed_at"] == "2026-07-15"

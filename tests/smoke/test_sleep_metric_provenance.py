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
               awake_sleep_minutes, sleep_score_source, sleep_efficiency_source
        FROM sleep_data WHERE date = '2026-07-15'
        """
    ).fetchone()
    conn.close()

    assert {
        "awake_sleep_minutes",
        "sleep_score_source",
        "sleep_efficiency_source",
    } <= columns
    assert row == (420, 55.0, 90.0, None, "legacy_unknown", "legacy_unknown")


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

"""Smoke coverage for issue #75 Garmin bio-signal collection."""
from __future__ import annotations

import pytest

from data.data_processor_phase1 import Phase1DataProcessor
from data.database import Database


pytestmark = pytest.mark.smoke


def test_phase1_daily_health_extracts_observational_bio_signals() -> None:
    payload = Phase1DataProcessor.process_daily_health_data(
        {
            "totalSteps": 7200,
            "totalDistanceMeters": 5100,
            "activeKilocalories": 420,
            "bmrKilocalories": 1650,
            "vigorousIntensityMinutes": 12,
            "moderateIntensityMinutes": 18,
        },
        {"restingHeartRate": 49},
        respiration_data={
            "dailyRespirationDTO": {
                "avgWakingRespirationValue": 13.2,
                "lowestRespirationValue": 9.0,
                "highestRespirationValue": 18.0,
            }
        },
        spo2_data={"dailySpO2DTO": {"averageSpO2": 96.4, "lowestSpO2": 91.0}},
        skin_temperature_data={"dailySkinTemperatureDTO": {"avgSkinTempCelsius": 33.1}},
    )

    assert payload is not None
    assert payload["resting_hr"] == 49
    assert payload["respiration_avg"] == pytest.approx(13.2)
    assert payload["respiration_min"] == pytest.approx(9.0)
    assert payload["respiration_max"] == pytest.approx(18.0)
    assert payload["spo2_avg"] == pytest.approx(96.4)
    assert payload["spo2_min"] == pytest.approx(91.0)
    assert payload["skin_temperature_avg"] == pytest.approx(33.1)


def test_daily_health_persists_bio_signal_columns(tmp_path) -> None:
    database = Database(str(tmp_path / "bio_signals.db"))

    result = database.sync_daily_health(
        {
            "2026-07-04": {
                "resting_hr": 48,
                "steps": 10000,
                "respiration_avg": 12.8,
                "respiration_min": 8.9,
                "respiration_max": 17.5,
                "spo2_avg": 97.2,
                "spo2_min": 92.0,
                "skin_temperature_avg": 32.9,
            }
        }
    )

    assert result == {"new": 1, "updated": 0}
    frame = database.get_daily_health(days=7)

    assert {"respiration_avg", "spo2_avg", "skin_temperature_avg"} <= set(frame.columns)
    row = frame.iloc[0]
    assert row["respiration_avg"] == pytest.approx(12.8)
    assert row["respiration_min"] == pytest.approx(8.9)
    assert row["respiration_max"] == pytest.approx(17.5)
    assert row["spo2_avg"] == pytest.approx(97.2)
    assert row["spo2_min"] == pytest.approx(92.0)
    assert row["skin_temperature_avg"] == pytest.approx(32.9)


def test_daily_health_resync_preserves_bio_signals_when_endpoints_fail(tmp_path) -> None:
    """Issue #88: ре-синк без опциональных payload'ов не должен затирать наблюдения NULL-ами."""
    database = Database(str(tmp_path / "bio_signals.db"))

    database.sync_daily_health(
        {
            "2026-07-04": {
                "resting_hr": 48,
                "steps": 10000,
                "respiration_avg": 12.8,
                "spo2_avg": 97.2,
                "spo2_min": 92.0,
                "skin_temperature_avg": 32.9,
            }
        }
    )

    # Повторный sync того же дня: respiration/SpO2/skin-temp эндпоинты не вернули данных
    result = database.sync_daily_health(
        {"2026-07-04": {"resting_hr": 50, "steps": 11000}}
    )

    assert result == {"new": 0, "updated": 1}
    row = database.get_daily_health(days=7).iloc[0]
    assert row["resting_hr"] == 50
    assert row["steps"] == 11000
    assert row["respiration_avg"] == pytest.approx(12.8)
    assert row["spo2_avg"] == pytest.approx(97.2)
    assert row["spo2_min"] == pytest.approx(92.0)
    assert row["skin_temperature_avg"] == pytest.approx(32.9)


def test_daily_health_bio_only_resync_preserves_legacy_fields(tmp_path) -> None:
    """Issue #88: день, где сработал только SpO2, не должен обнулять resting_hr/steps."""
    database = Database(str(tmp_path / "bio_signals.db"))

    database.sync_daily_health({"2026-07-04": {"resting_hr": 48, "steps": 10000}})

    result = database.sync_daily_health(
        {"2026-07-04": {"spo2_avg": 96.5, "spo2_min": 92.0}}
    )

    assert result == {"new": 0, "updated": 1}
    row = database.get_daily_health(days=7).iloc[0]
    assert row["resting_hr"] == 48
    assert row["steps"] == 10000
    assert row["spo2_avg"] == pytest.approx(96.5)
    assert row["spo2_min"] == pytest.approx(92.0)

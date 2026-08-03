"""BDD gates for #349: Streamlit display aggregations move to shared layer.

The extracted helpers must return exactly what the previous inline pandas
expressions produced (no formula change), and the four Streamlit pages must
consume the shared module instead of re-implementing the math.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.athlete_aggregates import (
    activity_totals,
    daily_activity_totals,
    hrv_baseline_rmssd,
    hrv_training_correlations,
    sleep_averages,
    sport_distribution,
)


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]
PAGES = {
    "dashboard": REPO_ROOT / "ui/pages/dashboard.py",
    "hrv": REPO_ROOT / "ui/pages/hrv.py",
    "activities": REPO_ROOT / "ui/pages/activities.py",
    "sleep": REPO_ROOT / "ui/pages/sleep.py",
}


def _activities_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "activity_id": ["a", "b", "c"],
            "date": pd.to_datetime(["2026-08-01", "2026-08-02", "2026-08-02"]),
            "sport": ["running", "cycling", "running"],
            "distance_km": [10.0, 20.0, 5.0],
            "duration_minutes": [60, 120, 30],
            "tss": [50.0, 80.0, 30.0],
        }
    )


def test_activity_totals_match_previous_inline_math():
    df = _activities_df()

    totals = activity_totals(df)

    assert totals["count"] == len(df) == 3
    assert totals["distance_km"] == round(df["distance_km"].sum(), 1)
    assert totals["duration_hours"] == round(df["duration_minutes"].sum() / 60.0, 1)
    assert totals["avg_tss"] == round(df["tss"].mean(), 0)


def test_daily_activity_totals_group_by_calendar_date():
    df = _activities_df()

    daily = daily_activity_totals(df, columns=("duration_minutes", "tss"))

    assert sorted(daily["date"].tolist()) == [
        pd.Timestamp("2026-08-01").date(),
        pd.Timestamp("2026-08-02").date(),
    ]
    second = daily.loc[daily["date"] == pd.Timestamp("2026-08-02").date()].iloc[0]
    assert second["duration_minutes"] == 150.0
    assert second["tss"] == 110.0


def test_sport_distribution_counts_sessions():
    dist = sport_distribution(_activities_df())

    assert dist["running"] == 2
    assert dist["cycling"] == 1


def test_hrv_baseline_and_correlations_match_previous_math():
    combined = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"]
            ),
            "rmssd": [30.0, 40.0, 35.0, 45.0],
            "tss": [100.0, 0.0, 50.0, 120.0],
        }
    )

    assert hrv_baseline_rmssd(combined) == combined["rmssd"].mean()

    corr = hrv_training_correlations(combined)
    same_day = combined[["rmssd", "tss"]].corr().iloc[0, 1]
    shifted = combined.copy()
    shifted["tss_prev"] = shifted["tss"].shift(1)
    lag1 = shifted[["rmssd", "tss_prev"]].corr().iloc[0, 1]
    shifted["tss_3day"] = shifted["tss"].rolling(window=3, min_periods=1).sum()
    cumulative = shifted[["rmssd", "tss_3day"]].corr().iloc[0, 1]
    assert corr["same_day"] == same_day
    assert corr["lag1"] == lag1
    assert corr["cumulative_3day"] == cumulative


def test_sleep_averages_match_previous_math():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-01", "2026-08-02"]),
            "sleep_score": [70.0, 80.0],
            "total_sleep_minutes": [420, 480],
            "sleep_efficiency": [85.0, 90.0],
            "awakenings_count": [2.0, 1.0],
        }
    )

    averages = sleep_averages(df)

    assert averages["score"] == df["sleep_score"].mean()
    assert averages["hours"] == df["total_sleep_minutes"].mean() / 60
    assert averages["efficiency"] == df["sleep_efficiency"].mean()
    assert averages["awakenings"] == df["awakenings_count"].mean()


def test_pages_consume_shared_aggregates_without_inline_math():
    for name, path in PAGES.items():
        assert "services.athlete_aggregates" in path.read_text(encoding="utf-8")

    dashboard = PAGES["dashboard"].read_text(encoding="utf-8")
    assert "['distance_km'].sum()" not in dashboard
    assert "['duration_minutes'].sum()" not in dashboard
    assert "['tss'].mean()" not in dashboard

    hrv = PAGES["hrv"].read_text(encoding="utf-8")
    assert '["rmssd"].mean()' not in hrv
    assert '["rmssd", "tss_prev"]].corr()' not in hrv

    activities = PAGES["activities"].read_text(encoding="utf-8")
    assert "['distance_km'].sum()" not in activities

    sleep = PAGES["sleep"].read_text(encoding="utf-8")
    assert "['sleep_score'].mean()" not in sleep

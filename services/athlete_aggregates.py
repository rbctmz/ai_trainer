"""Display aggregations shared by the legacy Streamlit pages (issue #349).

Pure pandas helpers extracted from ``ui/pages/{dashboard,hrv,activities,sleep}.py``
so the same math is testable and not duplicated in the legacy surface. The
formulas mirror the previous inline expressions exactly; this module imports no
Streamlit code and only depends on pandas.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence

import pandas as pd


def activity_totals(df: pd.DataFrame) -> Dict[str, Any]:
    """Count, total distance, total duration hours and average TSS."""
    count = int(len(df))
    distance_km = (
        round(float(df["distance_km"].sum()), 1) if "distance_km" in df.columns else 0.0
    )
    duration_hours = (
        round(float(df["duration_minutes"].sum()) / 60.0, 1)
        if "duration_minutes" in df.columns
        else 0.0
    )
    avg_tss = 0.0
    if "tss" in df.columns:
        valid = df["tss"].notna()
        avg_tss = round(float(df.loc[valid, "tss"].mean()), 0) if valid.any() else 0.0
    return {
        "count": count,
        "distance_km": distance_km,
        "duration_hours": duration_hours,
        "avg_tss": avg_tss,
    }


def daily_activity_totals(
    df: pd.DataFrame,
    columns: Sequence[str] = ("duration_minutes", "tss", "distance_km"),
) -> pd.DataFrame:
    """Sum the requested numeric columns per calendar date."""
    frame = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(frame["date"]):
        frame["date"] = pd.to_datetime(frame["date"])
    wanted = [column for column in columns if column in frame.columns]
    grouped = frame.groupby(frame["date"].dt.date).agg({column: "sum" for column in wanted})
    return grouped.reset_index()


def sport_distribution(df: pd.DataFrame) -> Dict[str, int]:
    """Session count per sport."""
    return {
        str(sport): int(count)
        for sport, count in df["sport"].value_counts().items()
    }


def hrv_baseline_rmssd(df: pd.DataFrame) -> float:
    """Baseline RMSSD as the window mean (previous inline math)."""
    return float(df["rmssd"].mean())


def hrv_training_correlations(combined: pd.DataFrame) -> Dict[str, Any]:
    """HRV×TSS correlations: same-day, one-day lag, 3-day cumulative load."""
    same_day = combined[["rmssd", "tss"]].corr().iloc[0, 1]
    shifted = combined.copy()
    shifted["tss_prev"] = shifted["tss"].shift(1)
    lag1 = shifted[["rmssd", "tss_prev"]].corr().iloc[0, 1]
    shifted["tss_3day"] = shifted["tss"].rolling(window=3, min_periods=1).sum()
    cumulative = shifted[["rmssd", "tss_3day"]].corr().iloc[0, 1]
    return {
        "same_day": same_day,
        "lag1": lag1,
        "cumulative_3day": cumulative,
    }


def sleep_averages(df: pd.DataFrame) -> Dict[str, float]:
    """Window averages for score, hours, efficiency and awakenings."""
    return {
        "score": float(df["sleep_score"].mean()),
        "hours": float(df["total_sleep_minutes"].mean()) / 60,
        "efficiency": float(df["sleep_efficiency"].mean()),
        "awakenings": float(df["awakenings_count"].mean()),
    }

"""Sleep summary endpoint: latest night, stage split, 30-day trend.

Pure read over the local cache; mirrors the HRV endpoint shape.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends

from api.deps import get_database
from data.database import Database

router = APIRouter(prefix="/api/sleep", tags=["sleep"])


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


@router.get("/summary")
def sleep_summary(days: int = 30, db: Database = Depends(get_database)) -> dict[str, Any]:
    df = db.get_sleep_data(days)
    if df is None or df.empty:
        return {"has_data": False, "latest": None, "averages": None, "trend": []}

    df = df.sort_values("date")
    latest = df.iloc[-1]

    def hours(minutes: Any) -> float | None:
        v = _num(minutes)
        return round(v / 60, 1) if v is not None else None

    trend = [
        {
            "date": pd.to_datetime(row["date"]).strftime("%Y-%m-%d"),
            "hours": hours(row.get("total_sleep_minutes")) or 0,
            "score": _num(row.get("sleep_score")),
        }
        for _, row in df.iterrows()
    ]

    avg_hours = hours(df["total_sleep_minutes"].mean()) if "total_sleep_minutes" in df else None
    avg_score = _num(df["sleep_score"].mean()) if "sleep_score" in df else None

    return {
        "has_data": True,
        "latest": {
            "date": pd.to_datetime(latest["date"]).strftime("%Y-%m-%d"),
            "hours": hours(latest.get("total_sleep_minutes")),
            "score": _num(latest.get("sleep_score")),
            "efficiency": _num(latest.get("sleep_efficiency")),
            "awakenings": _num(latest.get("awakenings_count")),
            "stages": {
                "deep": hours(latest.get("deep_sleep_minutes")),
                "light": hours(latest.get("light_sleep_minutes")),
                "rem": hours(latest.get("rem_sleep_minutes")),
            },
        },
        "averages": {"hours": avg_hours, "score": avg_score, "window_days": len(df)},
        "trend": trend,
    }

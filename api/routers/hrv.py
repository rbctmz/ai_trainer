"""HRV summary endpoint: latest value, baseline, 30-day trend, signals.

Reuses HRVAnalyzer for the AI-Endurance-style recovery score. Pure read; no
recomputation of training metrics here.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends

from api.deps import get_database
from data.database import Database
from models.hrv_analyzer import HRVAnalyzer
from utils.product_semantics import format_date_label

router = APIRouter(prefix="/api/hrv", tags=["hrv"])


@router.get("/summary")
def hrv_summary(days: int = 30, db: Database = Depends(get_database)) -> dict[str, Any]:
    df = db.get_hrv_data(days)
    if df is None or df.empty:
        return {"has_data": False, "latest": None, "baseline": None, "trend": [], "signals": []}

    df = df.dropna(subset=["rmssd"]).sort_values("date")
    if df.empty:
        return {"has_data": False, "latest": None, "baseline": None, "trend": [], "signals": []}

    latest_row = df.iloc[-1]
    latest_rmssd = float(latest_row["rmssd"])
    baseline = float(df["rmssd"].mean())

    score, info = HRVAnalyzer.recovery_score_advanced(db.get_hrv_data(max(days, 60)))

    trend = [
        {
            "date": pd.to_datetime(row["date"]).strftime("%Y-%m-%d"),
            "date_label": format_date_label(row["date"]),
            "rmssd": round(float(row["rmssd"]), 1),
        }
        for _, row in df.iterrows()
    ]

    signals = _build_signals(latest_rmssd, baseline)

    return {
        "has_data": True,
        "latest": {
            "date": pd.to_datetime(latest_row["date"]).strftime("%Y-%m-%d"),
            "date_label": format_date_label(latest_row["date"]),
            "rmssd": round(latest_rmssd, 1),
            "recovery_score": round(score, 0) if score is not None else None,
            "recovery_info": info,
        },
        "baseline": {"rmssd": round(baseline, 1), "window_days": len(df)},
        "trend": trend,
        "signals": signals,
    }


def _build_signals(latest: float, baseline: float) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    if baseline > 0 and latest < baseline * 0.8:
        signals.append(
            {
                "severity": "warning",
                "label": f"HRV {latest:.0f} ниже базовой {baseline:.0f} на 20%+",
            }
        )
    if latest < 30:
        signals.append({"severity": "warning", "label": "Низкий RMSSD — фокус на восстановлении"})
    elif latest > 50:
        signals.append({"severity": "success", "label": "Высокий RMSSD — организм готов к нагрузкам"})
    if not signals:
        signals.append({"severity": "neutral", "label": "HRV в пределах нормы"})
    return signals

"""Activities endpoint: recent training sessions from the local cache."""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends

from api.deps import get_database
from data.database import Database
from utils.product_semantics import format_date_label, normalize_sport_key, sport_label

router = APIRouter(prefix="/api/activities", tags=["activities"])

_NUMERIC = (
    "duration_minutes",
    "moving_duration_minutes",
    "distance_km",
    "tss",
    "source_tss",
    "avg_hr",
    "max_hr",
    "elevation_gain",
    "calories",
)


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


@router.get("")
def list_activities(days: int = 30, db: Database = Depends(get_database)) -> dict[str, Any]:
    df = db.get_activities(days)
    if df is None or df.empty:
        return {"has_data": False, "count": 0, "totals": {}, "items": []}

    df = df.sort_values("date", ascending=False)
    items = []
    for _, row in df.iterrows():
        raw_sport = row.get("sport") or "—"
        tss_method = _text(row.get("tss_method"))
        source_tss = _num(row.get("source_tss"))
        if tss_method == "garmin_training_load":
            tss_source = "garmin"
        elif tss_method:
            tss_source = "computed"
        elif source_tss is not None:
            tss_source = "garmin"
        else:
            tss_source = "unknown"
        items.append(
            {
                "activity_id": str(row.get("activity_id")),
                "date": pd.to_datetime(row["date"]).strftime("%Y-%m-%d"),
                "date_label": format_date_label(row.get("date")),
                "sport": normalize_sport_key(raw_sport),
                "sport_label": sport_label(raw_sport),
                **{key: _num(row.get(key)) for key in _NUMERIC},
                "tss_method": tss_method,
                "tss_source": tss_source,
            }
        )

    totals = {
        "count": int(len(df)),
        "distance_km": _num(df["distance_km"].sum()) if "distance_km" in df else None,
        "duration_hours": _num(df["duration_minutes"].sum() / 60) if "duration_minutes" in df else None,
        "tss": _num(df["tss"].sum()) if "tss" in df else None,
    }

    return {"has_data": True, "count": int(len(df)), "totals": totals, "items": items}

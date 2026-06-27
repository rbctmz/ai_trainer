"""Activities endpoint: recent training sessions from the local cache."""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends

from api.deps import get_database
from data.database import Database

router = APIRouter(prefix="/api/activities", tags=["activities"])

_NUMERIC = ("duration_minutes", "distance_km", "tss", "avg_hr", "max_hr", "elevation_gain", "calories")


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
        items.append(
            {
                "activity_id": str(row.get("activity_id")),
                "date": pd.to_datetime(row["date"]).strftime("%Y-%m-%d"),
                "sport": str(row.get("sport") or "—"),
                **{key: _num(row.get(key)) for key in _NUMERIC},
            }
        )

    totals = {
        "count": int(len(df)),
        "distance_km": _num(df["distance_km"].sum()) if "distance_km" in df else None,
        "duration_hours": _num(df["duration_minutes"].sum() / 60) if "duration_minutes" in df else None,
        "tss": _num(df["tss"].sum()) if "tss" in df else None,
    }

    return {"has_data": True, "count": int(len(df)), "totals": totals, "items": items}

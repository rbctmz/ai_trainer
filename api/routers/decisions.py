"""Coach decision audit trail endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.deps import get_database
from api.operational_state import build_operational_state
from data.database import Database

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("")
def list_decisions(
    days: int = 30,
    demo: bool = False,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    rows = [row for row in db.get_coach_decisions(days=days) if row]
    grouped: list[dict[str, Any]] = []
    by_date: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        day = str(row.get("date") or "")[:10]
        if not day:
            continue
        item = dict(row)
        item["time"] = _format_time(item.get("date"))
        if day not in by_date:
            by_date[day] = []
            grouped.append({"date": day, "decisions": by_date[day]})
        by_date[day].append(item)

    has_data = bool(grouped)
    latest_data_at = grouped[0]["date"] if grouped else None
    return {
        "has_data": has_data,
        "count": len(rows),
        "days": grouped,
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=has_data,
            latest_data_at=latest_data_at,
            stale_after_days=30,
        ),
    }


def _format_time(value: Any) -> str:
    text = str(value or "")
    if "T" in text:
        return text.split("T", 1)[1][:5]
    if " " in text:
        return text.split(" ", 1)[1][:5]
    return ""

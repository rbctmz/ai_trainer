"""Read-only adherence ribbon endpoint (Issue #228)."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends

from api.deps import get_database
from data.database import Database
from models.adherence_ribbon import build_adherence_ribbon
from services.reconciliation import reconciliation_at

router = APIRouter(prefix="/api/adherence", tags=["adherence"])

_MAX_WEEKS = 8


@router.get("")
def get_adherence(
    weeks: int = 4,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    """Лента план vs факт: дневные статусы + недельные агрегаты.

    Read-only и строго без live-provider вызовов на рендер-пути
    (``include_provider=False``): лента — витрина доверия, а не синк.
    """
    resolved_weeks = max(1, min(_MAX_WEEKS, int(weeks or 1)))
    snapshot = reconciliation_at(
        db,
        weeks=resolved_weeks,
        include_provider=False,
    )
    as_of = None
    try:
        as_of = date.fromisoformat(str(snapshot.get("as_of") or "")[:10])
    except ValueError:
        as_of = None
    ribbon = build_adherence_ribbon(
        snapshot,
        as_of=as_of or date.today(),
        weeks=resolved_weeks,
    )
    return {**ribbon, "weeks_requested": resolved_weeks}

"""FastAPI adapter for the headless daily decision snapshot."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.deps import get_database
from api.today_snapshot import build_today_decision_snapshot
from data.database import Database

router = APIRouter(prefix="/api/today", tags=["today"])


@router.get("")
def today_view(
    demo: bool = False,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    return build_today_decision_snapshot(db, demo=demo)

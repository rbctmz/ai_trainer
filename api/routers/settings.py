"""FastAPI contract for athlete-facing rendering settings.

GET/PUT /api/settings/briefing — issue #235 briefing frequency (daily vs
conflicts-only /today rendering). Persisted via the generic user_settings
key/value table; demo isolation follows the same ``?demo=1`` -> isolated DB
routing as every other endpoint (api/deps.py::get_database).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.briefing_settings import get_briefing_frequency, set_briefing_frequency
from api.deps import get_database
from data.database import Database

router = APIRouter(prefix="/api/settings", tags=["settings"])


class BriefingFrequencyRequest(BaseModel):
    frequency: Literal["daily", "conflicts_only"]


class BriefingFrequencyResponse(BaseModel):
    frequency: str


@router.get("/briefing")
def get_briefing_settings(db: Database = Depends(get_database)) -> BriefingFrequencyResponse:
    return BriefingFrequencyResponse(frequency=get_briefing_frequency(db))


@router.put("/briefing")
def put_briefing_settings(
    payload: BriefingFrequencyRequest,
    db: Database = Depends(get_database),
) -> BriefingFrequencyResponse:
    frequency = set_briefing_frequency(db, payload.frequency)
    return BriefingFrequencyResponse(frequency=frequency)


__all__ = [
    "router",
    "BriefingFrequencyRequest",
    "BriefingFrequencyResponse",
    "get_briefing_settings",
    "put_briefing_settings",
]

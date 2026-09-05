"""FastAPI contract for athlete-facing rendering settings.

GET/PUT /api/settings/briefing — issue #235 briefing frequency (daily vs
conflicts-only /today rendering). Persisted via the generic user_settings
key/value table; demo isolation follows the same ``?demo=1`` -> isolated DB
routing as every other endpoint (api/deps.py::get_database).
"""
from __future__ import annotations

from typing import Literal
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.briefing_settings import get_briefing_frequency, set_briefing_frequency
from api.deps import get_database
from data.database import Database
from models.coach_decisions import NO_REVISIT_REQUIRED
from services.agent_log import record_agent_decision

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
    previous = get_briefing_frequency(db)
    frequency = set_briefing_frequency(db, payload.frequency)
    event_token = str(uuid.uuid4())
    record_agent_decision(
        db,
        decision_type="Monitor",
        reason=f"Частота брифинга: {previous} → {frequency}.",
        decision_event_id=f"settings_change:{event_token}",
        trigger="settings_change",
        trigger_source=f"settings:briefing:{event_token}",
        scope="plan",
        outcome="no_change" if previous == frequency else "applied",
        revisit_reason=NO_REVISIT_REQUIRED,
    )
    return BriefingFrequencyResponse(frequency=frequency)


__all__ = [
    "router",
    "BriefingFrequencyRequest",
    "BriefingFrequencyResponse",
    "get_briefing_settings",
    "put_briefing_settings",
]

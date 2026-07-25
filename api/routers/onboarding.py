"""FastAPI-контракт онбординга планирования (#271, M2 §4).

`GET  /api/onboarding/planning` → сохранённый профиль (если есть), предложение по
данным атлета и контекст гонок.
`PUT  /api/onboarding/planning` → валидация и сохранение профиля; 422 на мусор.

Эндпоинт намеренно НЕ строит план: построение остаётся за
`POST /api/planning/build` с его preview-гейтом 409. Профиль — это вход; план —
решение с checkpoint'ом и журналом. Склеенные в один вызов, они лишили бы атлета
возможности посмотреть план до сохранения.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictFloat, StrictInt

from api.deps import get_database
from data.database import Database
from services import planning_onboarding, planning_profile

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class PlanningProfileRequest(BaseModel):
    planning_mode: str
    intent: str
    goal_type: str
    distance: str
    available_hours: Union[StrictInt, StrictFloat]
    available_days: List[str]
    horizon_weeks: StrictInt
    source: Optional[str] = None


@router.get("/planning")
def get_planning_onboarding(db: Database = Depends(get_database)) -> Dict[str, Any]:
    event_context = planning_onboarding.resolve_event_context()
    status = planning_profile.profile_status(db)
    return {
        **status,
        "suggested": planning_onboarding.suggest_planning_defaults(
            db, event_context=event_context
        ),
        "event_context": event_context,
    }


@router.put("/planning")
def put_planning_onboarding(
    payload: PlanningProfileRequest,
    db: Database = Depends(get_database),
) -> Dict[str, Any]:
    body = payload.model_dump(exclude_none=True)
    try:
        profile = planning_profile.save_profile(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"completed": True, "profile": profile}


__all__ = ["router", "PlanningProfileRequest", "get_planning_onboarding", "put_planning_onboarding"]

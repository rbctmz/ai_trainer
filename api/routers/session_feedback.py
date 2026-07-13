"""FastAPI contracts for athlete-entered post-workout feedback."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_database
from api.session_feedback import (
    StaleFeedbackError,
    correct_session_feedback,
    dismiss_feedback_prompt,
    feedback_history,
    feedback_summary,
    list_feedback_prompts,
    submit_session_feedback,
    tombstone_session_feedback,
)
from data.database import Database


router = APIRouter(prefix="/api/session-feedback", tags=["session-feedback"])


class FeedbackValues(BaseModel):
    client_submission_fingerprint: str = Field(min_length=1, max_length=128)
    completion_status: str
    completion_pct: float | None = Field(default=None, ge=0, le=100)
    session_rpe_1_10: int | None = Field(default=None, ge=1, le=10)
    quality_rating_1_5: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=2000)


class SubmitFeedbackRequest(FeedbackValues):
    session_id: str = Field(min_length=1, max_length=200)


class TombstoneRequest(BaseModel):
    client_submission_fingerprint: str = Field(min_length=1, max_length=128)


class DismissPromptRequest(BaseModel):
    client_submission_fingerprint: str = Field(min_length=1, max_length=128)
    prompt_fingerprint: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=500)


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, StaleFeedbackError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("/prompts")
def pending_feedback_prompts(
    as_of: date | None = None,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    return list_feedback_prompts(db, as_of=as_of)


@router.post("")
def submit_feedback(
    payload: SubmitFeedbackRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    try:
        return submit_session_feedback(db, payload.dict())
    except (LookupError, StaleFeedbackError, ValueError) as exc:
        _raise_http(exc)
        raise AssertionError("unreachable")


@router.post("/{feedback_id}/correct")
def correct_feedback(
    feedback_id: int,
    payload: FeedbackValues,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    try:
        return correct_session_feedback(db, feedback_id, payload.dict())
    except (LookupError, StaleFeedbackError, ValueError) as exc:
        _raise_http(exc)
        raise AssertionError("unreachable")


@router.post("/{feedback_id}/tombstone")
def tombstone_feedback(
    feedback_id: int,
    payload: TombstoneRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    try:
        return tombstone_session_feedback(
            db,
            feedback_id,
            client_submission_fingerprint=payload.client_submission_fingerprint,
        )
    except (LookupError, StaleFeedbackError, ValueError) as exc:
        _raise_http(exc)
        raise AssertionError("unreachable")


@router.post("/prompts/{session_id}/dismiss")
def dismiss_prompt(
    session_id: str,
    payload: DismissPromptRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    return dismiss_feedback_prompt(
        db,
        session_id,
        client_submission_fingerprint=payload.client_submission_fingerprint,
        prompt_fingerprint=payload.prompt_fingerprint,
        reason=payload.reason,
    )


@router.get("/{session_id}/history")
def session_feedback_history(
    session_id: str,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    return feedback_history(db, session_id)


@router.get("/summary/all")
def session_feedback_summary(
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    return feedback_summary(db)


__all__ = ["router"]

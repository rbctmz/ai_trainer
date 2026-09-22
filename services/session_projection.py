"""Bounded provider-free read orchestration for the #609 session projection."""
from __future__ import annotations

from datetime import date
from typing import Any

from data.database import Database
from models.session_projection import build_session_projection
from services.reconciliation import reconciliation_at


def session_projection_at(
    db: Database,
    *,
    session_id: str,
    as_of: date | str | None = None,
    weeks: int = 1,
) -> dict[str, Any]:
    """Read one session projection strictly from bounded local evidence."""
    reconciliation = reconciliation_at(
        db,
        weeks=weeks,
        as_of=as_of,
        include_provider=False,
    )
    match_revision = db.get_latest_plan_actual_match_for_session(session_id)
    feedback = db.get_latest_session_feedback(session_id)
    return build_session_projection(
        reconciliation,
        session_id=session_id,
        match_revision=match_revision,
        feedback=feedback,
    )


__all__ = ["session_projection_at"]

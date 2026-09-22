"""Bounded provider-free read orchestration for the #609 session projection."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from data.database import Database
from models.session_projection import build_session_projection
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from models.session_identity import ensure_session_identities
from services.reconciliation import reconciliation_at


def _date_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "")[:10]
    return text or None


def _planned_session_date(db: Database, session_id: str) -> str | None:
    """Resolve a session's plan date without widening the evidence window."""
    plan = restore_goal_plan_from_checkpoint(db.get_latest_planning_checkpoint())
    if not plan:
        return None
    plan = ensure_session_identities(plan)
    daily_plan = list(plan.get("daily_plan") or [])
    for index, raw_template in enumerate(plan.get("session_templates") or []):
        if not isinstance(raw_template, Mapping):
            continue
        template = dict(raw_template)
        candidates = list(template.get("sessions") or []) or [template]
        if not any(
            isinstance(candidate, Mapping)
            and str(candidate.get("session_id") or "").strip() == session_id
            for candidate in candidates
        ):
            continue
        template_date = _date_text(template.get("date"))
        if template_date:
            return template_date
        if index < len(daily_plan):
            item = daily_plan[index]
            if isinstance(item, (list, tuple)) and item:
                return _date_text(item[0])
    return None


def session_projection_at(
    db: Database,
    *,
    session_id: str,
    as_of: date | str | None = None,
    weeks: int = 1,
) -> dict[str, Any]:
    """Read one session projection strictly from bounded local evidence."""
    resolved_as_of = as_of
    if resolved_as_of is None:
        resolved_as_of = _planned_session_date(db, session_id)
    reconciliation = reconciliation_at(
        db,
        weeks=weeks,
        as_of=resolved_as_of,
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

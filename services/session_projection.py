"""Bounded provider-free read orchestration for the #609 session projection."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from data.database import Database
from models.session_projection import build_session_projection
from models.plan_actual_reconciliation import (
    iter_parent_sessions,
    resolve_confirmed_replacement_ledger,
)
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
    return session_projection_from_reconciliation(
        db,
        reconciliation,
        session_id=session_id,
    )


def session_projection_from_reconciliation(
    db: Database,
    reconciliation: Mapping[str, Any],
    *,
    session_id: str,
) -> dict[str, Any]:
    """Compose one DTO from an already-bounded local reconciliation snapshot."""
    match_revision = _effective_match_revision(db, session_id)
    feedback = db.get_latest_session_feedback(session_id)
    return build_session_projection(
        reconciliation,
        session_id=session_id,
        match_revision=match_revision,
        feedback=feedback,
    )


def _effective_match_revision(
    db: Database,
    session_id: str,
) -> Mapping[str, Any] | None:
    """Return the match revision reconciliation uses for this active session.

    Reconciliation may inherit an explicit confirmation from a uniquely
    claimed replacement predecessor. Preserve that same ledger provenance in
    the projection instead of looking up only the replacement's new ID.
    """
    current = db.get_latest_plan_actual_match_for_session(session_id)
    if current is not None:
        return current

    checkpoint = db.get_latest_planning_checkpoint()
    plan = restore_goal_plan_from_checkpoint(checkpoint)
    if not plan:
        return None
    parent_sessions = iter_parent_sessions(plan.get("session_templates") or [])
    current_entry = next(
        (
            entry
            for entry in parent_sessions
            if str(entry["session"].get("session_id") or "").strip()
            == session_id
        ),
        None,
    )
    if current_entry is None:
        return None

    session_date = str(current_entry.get("date") or "")[:10]
    if not session_date:
        return None
    ledger_rows = db.get_latest_plan_actual_matches(
        start_date=session_date,
        end_date=session_date,
    )
    latest_ledger = {
        str(row.get("target_key")): row
        for row in ledger_rows or []
        if isinstance(row, Mapping) and row.get("target_key")
    }
    current_session_ids = {
        str(entry["session"].get("session_id") or "").strip()
        for entry in parent_sessions
        if str(entry["session"].get("session_id") or "").strip()
    }
    replacement_claim_counts: dict[str, int] = {}
    for entry in parent_sessions:
        predecessor_id = str(
            entry["session"].get("replaces_session_id") or ""
        ).strip()
        if predecessor_id:
            replacement_claim_counts[predecessor_id] = (
                replacement_claim_counts.get(predecessor_id, 0) + 1
            )

    session = current_entry["session"]
    predecessor_id = str(session.get("replaces_session_id") or "").strip()
    return resolve_confirmed_replacement_ledger(
        {"date": session_date, "sport": session.get("sport")},
        latest_ledger,
        predecessor_id=predecessor_id,
        current_session_ids=current_session_ids,
        replacement_claim_counts=replacement_claim_counts,
    )


__all__ = ["session_projection_at", "session_projection_from_reconciliation"]

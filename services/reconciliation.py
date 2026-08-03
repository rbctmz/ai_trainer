"""Plan-vs-actual reconciliation ownership (Issue #194).

This module owns `reconciliation_at`, the canonical `as_of` parser, and the
provider-evidence orchestration for plan/actual reconciliation. It was
extracted out of `api/planning_service.py`, which historically hosted this
orchestration logic even though the surrounding module exists to be the API
contract layer, not a home for service-layer business logic.
`api/planning_service.py::reconciliation_at` re-exports this module's
function directly (the same object, not a copy) so every existing caller
keeps working unchanged.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict

from data.database import Database
from models.plan_actual_reconciliation import build_reconciliation
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from models.session_identity import ensure_session_identities


_MAX_LOCAL_RECONCILIATION_WEEKS = 16
_MAX_PROVIDER_RECONCILIATION_WEEKS = 12


def _parse_as_of(value: date | str | None) -> date:
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError as exc:
            raise ValueError("as_of must be YYYY-MM-DD") from exc
    return datetime.now().date()


def _provider_reconciliation_evidence(
    start: date,
    end: date,
    *,
    include_provider: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not include_provider:
        return [], [], {"status": "disabled"}
    from services.intervals_icu import IntervalsICUError, get_client

    client = get_client()
    if not client.is_configured():
        return [], [], {"status": "not_configured"}
    try:
        activities = client.list_activities(start, end)
        events = client.list_workout_events(start, end)
    except IntervalsICUError as exc:
        return [], [], {"status": "unavailable", "error": str(exc)}
    return activities, events, {
        "status": "available",
        "activity_count": len(activities),
        "workout_event_count": len(events),
    }


def reconciliation_at(
    db: Database,
    *,
    weeks: int = 1,
    as_of: date | str | None = None,
    include_provider: bool = True,
) -> Dict[str, Any]:
    latest = db.get_latest_planning_checkpoint()
    goal_plan = restore_goal_plan_from_checkpoint(latest)
    if not goal_plan or not goal_plan.get("daily_plan"):
        return {"has_plan": False, "rows": [], "unplanned_activities": []}
    goal_plan = ensure_session_identities(goal_plan)
    resolved_as_of = _parse_as_of(as_of)
    max_weeks = (
        _MAX_PROVIDER_RECONCILIATION_WEEKS
        if include_provider
        else _MAX_LOCAL_RECONCILIATION_WEEKS
    )
    resolved_weeks = max(1, min(max_weeks, int(weeks or 1)))
    start = resolved_as_of - timedelta(days=resolved_weeks * 7 - 1)
    provider_activities, provider_events, provider = _provider_reconciliation_evidence(
        start,
        resolved_as_of,
        include_provider=include_provider,
    )
    ledger_rows = db.get_latest_plan_actual_matches(
        start_date=start.isoformat(),
        end_date=resolved_as_of.isoformat(),
    )
    payload = build_reconciliation(
        goal_plan,
        db.get_activities_between(start.isoformat(), resolved_as_of.isoformat()),
        as_of=resolved_as_of,
        weeks=resolved_weeks,
        base_checkpoint_id=int(latest.get("id")),
        provider_activities=provider_activities,
        provider_events=provider_events,
        ledger_rows=ledger_rows,
    )
    if provider.get("status") == "unavailable":
        quality = dict(payload.get("data_quality") or {})
        reasons = list(quality.get("reasons") or [])
        if "provider_unavailable" not in reasons:
            reasons.append("provider_unavailable")
        quality["status"] = "data_gap"
        quality["reasons"] = reasons
        payload["data_quality"] = quality
    return {"has_plan": True, **payload, "provider": provider}

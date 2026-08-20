"""Coach decision audit trail endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api import planning_service
from api.deps import get_database
from api.operational_state import build_operational_state
from data.database import Database
from services.intervals_plan_delivery import safe_deliver_active_plan

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("")
def list_decisions(
    days: int = 30,
    demo: bool = False,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    rows = [row for row in db.get_coach_decisions(days=days) if row]
    proposal_rows = [row for row in db.get_coach_proposals(days=days) if row]
    recovery_rows = [row for row in db.get_recovery_decisions(days=days) if row]
    grouped: list[dict[str, Any]] = []
    by_date: dict[str, list[dict[str, Any]]] = {}
    proposal_grouped: list[dict[str, Any]] = []
    proposals_by_date: dict[str, list[dict[str, Any]]] = {}
    pending_proposal_grouped: list[dict[str, Any]] = []
    pending_proposals_by_date: dict[str, list[dict[str, Any]]] = {}
    pending_proposal_count = 0
    recovery_grouped: list[dict[str, Any]] = []
    recovery_by_date: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        day = str(row.get("date") or "")[:10]
        if not day:
            continue
        item = dict(row)
        item["time"] = _display_time(item)
        item["count"] = 1
        item["first_time"] = item["time"]
        if day not in by_date:
            by_date[day] = []
            grouped.append({"date": day, "decisions": by_date[day]})
        day_items = by_date[day]
        previous = day_items[-1] if day_items else None
        # Rows arrive newest-first, so a repeated recommendation extends the
        # previous group backwards in time: keep the newest row as the face of
        # the group and push first_time to the earliest occurrence.
        if (
            previous is not None
            and previous.get("decision_type") == item.get("decision_type")
            and previous.get("reason") == item.get("reason")
        ):
            previous["count"] += 1
            previous["first_time"] = item["time"]
        else:
            day_items.append(item)

    for row in proposal_rows:
        day = str(row.get("date") or "")[:10]
        if not day:
            continue
        item = dict(row)
        item["time"] = _display_time(item)
        if day not in proposals_by_date:
            proposals_by_date[day] = []
            proposal_grouped.append({"date": day, "proposals": proposals_by_date[day]})
        proposals_by_date[day].append(item)
        if item.get("status") == "pending":
            pending_proposal_count += 1
            if day not in pending_proposals_by_date:
                pending_proposals_by_date[day] = []
                pending_proposal_grouped.append(
                    {"date": day, "proposals": pending_proposals_by_date[day]}
                )
            pending_proposals_by_date[day].append(item)

    for row in recovery_rows:
        day = str(row.get("date") or "")[:10]
        if not day:
            continue
        item = dict(row)
        item["time"] = _display_time(item)
        item["conflict_rules"] = _dedupe_conflict_rules(
            (item.get("report") or {}).get("conflicts")
        )
        if day not in recovery_by_date:
            recovery_by_date[day] = []
            recovery_grouped.append(
                {"date": day, "recovery_decisions": recovery_by_date[day]}
            )
        recovery_by_date[day].append(item)

    has_data = bool(grouped or proposal_grouped or recovery_grouped)
    latest_dates = [
        group[0]["date"]
        for group in (grouped, proposal_grouped, recovery_grouped)
        if group
    ]
    latest_data_at = max(latest_dates) if latest_dates else None
    return {
        "has_data": has_data,
        "count": len(rows),
        "days": grouped,
        "proposal_count": len(proposal_rows),
        "proposal_days": proposal_grouped,
        "pending_proposal_count": pending_proposal_count,
        "pending_proposal_days": pending_proposal_grouped,
        "recovery_count": len(recovery_rows),
        "recovery_days": recovery_grouped,
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=has_data,
            latest_data_at=latest_data_at,
            stale_after_days=30,
        ),
    }


def _format_time(value: Any) -> str:
    text = str(value or "")
    if "T" in text:
        return text.split("T", 1)[1][:5]
    if " " in text:
        return text.split(" ", 1)[1][:5]
    return ""


def _display_time(row: dict[str, Any]) -> str:
    """Clock time to show for one audit row.

    Recovery decisions and recovery/plan-loop proposals persist `date` as a
    pure business date (`<as_of>T00:00:00`), so their real creation clock lives
    in `created_at`. Coach decisions (and coach-created proposals) carry their
    real time-of-day in `date` itself. Prefer `date`'s time, and fall back to
    `created_at` only when `date` has no meaningful time (`00:00` or absent) —
    both columns already store the same UTC-based clock, so the fallback stays
    consistent with the times this surface has always shown.
    """
    from_date = _format_time(row.get("date"))
    if from_date and from_date != "00:00":
        return from_date
    return _format_time(row.get("created_at")) or from_date


def _dedupe_conflict_rules(conflicts: Any) -> list[dict[str, str]]:
    """Collapse a readiness report's conflicts to one row per unique
    (severity, rule) pair, preserving first-seen order.

    `detect_readiness_conflicts` emits one conflict per upcoming session, so a
    single readiness state colliding with the same session role across several
    days yields several conflicts that share `severity`/`kind` and differ only
    by date. The audit trail keeps every conflict; this is the display
    projection the /decisions recovery card renders — it shows `severity·kind`
    only, so identical rule rows must not repeat.
    """
    rules: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for conflict in conflicts or []:
        if not isinstance(conflict, dict):
            continue
        severity = str(conflict.get("severity") or "")
        kind = str(conflict.get("kind") or "readiness conflict")
        key = (severity, kind)
        if key in seen:
            continue
        seen.add(key)
        rules.append({"severity": severity, "kind": kind})
    return rules


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: int,
    variant_kind: str | None = None,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    proposal = _pending_proposal_or_error(db, proposal_id)
    if proposal.get("action") == "recovery_replan":
        proposal_preview = proposal.get("preview")
        try:
            _resolve_recovery_variant_kind(
                proposal_preview if isinstance(proposal_preview, dict) else {},
                variant_kind,
            )
        except ValueError as exc:
            # Client selection errors are recoverable: validate against this
            # proposal's own immutable preview before claiming it. The athlete
            # can immediately choose an offered variant; no plan/provider
            # mutation has started.
            raise HTTPException(status_code=422, detail=str(exc))
    proposal = db.transition_coach_proposal_status(
        proposal_id,
        "pending",
        "applying",
    )
    if proposal is None:
        raise HTTPException(status_code=409, detail="proposal is already being applied")
    try:
        result = _apply_proposal(db, proposal, variant_kind=variant_kind)
    except planning_service.StalePlanningCheckpointError as exc:
        db.update_coach_proposal_status(proposal_id, "failed", error=str(exc))
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        db.update_coach_proposal_status(proposal_id, "failed", error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        db.update_coach_proposal_status(proposal_id, "failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    if (
        proposal.get("action") == "recovery_replan"
        and result.get("selected_kind") in _RECOVERY_DELIVERY_KINDS
    ):
        result = {
            **result,
            "delivery": safe_deliver_active_plan(
                db,
                dates=list(result.get("affected_dates") or []),
                source="recovery_approve",
            ),
        }

    updated = db.update_coach_proposal_status(proposal_id, "approved", result=result)
    return {"proposal": updated, "result": result}


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: int,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    _pending_proposal_or_error(db, proposal_id)
    updated = db.transition_coach_proposal_status(proposal_id, "pending", "rejected")
    if updated is None:
        raise HTTPException(status_code=409, detail="proposal is already being resolved")
    updated = db.update_coach_proposal_status(
        proposal_id,
        "rejected",
        result={"message": "rejected by user"},
    )
    return {"proposal": updated}


@router.post("/proposals/{proposal_id}/rollback")
def rollback_proposal(
    proposal_id: int,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    proposal = _approved_recovery_proposal_or_error(db, proposal_id)
    proposal = db.transition_coach_proposal_status(
        proposal_id,
        "approved",
        "rolling_back",
    )
    if proposal is None:
        raise HTTPException(status_code=409, detail="proposal is already being rolled back")
    try:
        rollback = planning_service.rollback_recovery_replan(
            db,
            proposal.get("result") or {},
            persist=True,
        )
    except planning_service.StalePlanningCheckpointError as exc:
        db.transition_coach_proposal_status(proposal_id, "rolling_back", "approved")
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        db.transition_coach_proposal_status(proposal_id, "rolling_back", "approved")
        raise HTTPException(status_code=422, detail=str(exc))

    prior_result = proposal.get("result") or {}
    affected_dates = list(prior_result.get("affected_dates") or [])
    selected_kind = str(prior_result.get("selected_kind") or "downgrade_today")
    if selected_kind in _RECOVERY_DELIVERY_KINDS:
        delivery = safe_deliver_active_plan(
            db,
            dates=affected_dates,
            source="recovery_rollback",
        )
    else:
        # #411 review P1: перенос тоже доставляется при approve, значит при
        # rollback надо вернуть события восстановленного плана. Skip остаётся
        # только для keep (план не менялся).
        delivery = {
            "status": "skipped",
            "retryable": False,
            "failed_count": 0,
            "dates": affected_dates,
        }
    rollback = {
        **rollback,
        "affected_dates": affected_dates,
        "delivery": delivery,
    }
    result = {
        **(proposal.get("result") or {}),
        "rollback": rollback,
        "delivery": rollback["delivery"],
    }
    updated = db.update_coach_proposal_status(
        proposal_id,
        "rolled_back",
        result=result,
    )
    return {"proposal": updated, "result": rollback}


def _pending_proposal_or_error(db: Database, proposal_id: int) -> dict[str, Any]:
    proposal = db.get_coach_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal not found")
    if proposal.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"proposal is already {proposal.get('status')}")
    return proposal


def _approved_recovery_proposal_or_error(
    db: Database,
    proposal_id: int,
) -> dict[str, Any]:
    proposal = db.get_coach_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal not found")
    if proposal.get("action") != "recovery_replan":
        raise HTTPException(status_code=422, detail="proposal does not support rollback")
    if proposal.get("status") != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"proposal is already {proposal.get('status')}",
        )
    return proposal


# Issue #209 M4: the three decision-contract variant kinds a `recovery_replan`
# proposal's preview may offer (`preview["variants"][*]["kind"]`).
_RECOVERY_VARIANT_KINDS = {"keep", "downgrade_today", "transfer_1_3d"}
# #411: варианты, которые МЕНЯЮТ план и потому требуют доставки изменённых дат
# в Intervals.icu (keep ничего не меняет — provider не трогаем).
_RECOVERY_DELIVERY_KINDS = {"downgrade_today", "transfer_1_3d"}


def _resolve_recovery_variant_kind(
    preview: dict[str, Any],
    variant_kind: str | None,
) -> str:
    """Fail-closed resolution of the confirmed variant, from the proposal's
    OWN persisted preview only — never an arbitrary client payload.

    Omitted/explicit `None` preserves the legacy downgrade-only contract
    byte-for-byte. Any other value must be one of the proposal's own saved
    `preview["variants"][*]["kind"]` entries; an unknown kind or one that is
    currently unavailable (e.g. `transfer_1_3d` with no safe date) fails
    closed before any mutation.
    """
    if variant_kind is None:
        return "downgrade_today"
    if variant_kind not in _RECOVERY_VARIANT_KINDS:
        raise ValueError(f"unknown recovery variant kind: {variant_kind}")
    available_kinds = {str(v.get("kind")) for v in (preview or {}).get("variants") or []}
    if variant_kind not in available_kinds:
        raise ValueError(f"recovery variant '{variant_kind}' is not available for this proposal")
    return variant_kind


def _apply_recovery_replan_proposal(
    db: Database,
    proposal: dict[str, Any],
    params: dict[str, Any],
    variant_kind: str | None,
) -> dict[str, Any]:
    preview = proposal.get("preview") or {}
    resolved_kind = _resolve_recovery_variant_kind(
        preview if isinstance(preview, dict) else {}, variant_kind
    )

    if resolved_kind == "keep":
        # Audited no-op: the conflict is accepted as-is, no checkpoint, no
        # provider call.
        return {"selected_kind": "keep", "plan_id": None, "affected_dates": []}

    if resolved_kind == "downgrade_today":
        result = planning_service.apply_recovery_replan(db, params, persist=True)
        return {**result, "selected_kind": "downgrade_today"}

    transfer_preview = next(
        (v for v in preview.get("variants") or [] if v.get("kind") == "transfer_1_3d"),
        None,
    )
    if transfer_preview is None:
        raise ValueError("recovery transfer variant is not available for this proposal")
    result = planning_service.apply_recovery_replan_transfer(
        db,
        base_checkpoint_id=int(params.get("base_checkpoint_id")),
        session_id=str(transfer_preview.get("replaced_session_id") or ""),
        target_date=str(transfer_preview.get("target_date") or ""),
        persist=True,
    )
    return {**result, "selected_kind": "transfer_1_3d"}


def _apply_proposal(
    db: Database,
    proposal: dict[str, Any],
    *,
    variant_kind: str | None = None,
) -> dict[str, Any]:
    action = proposal.get("action")
    params = proposal.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("proposal params are invalid")

    if action == "build_plan":
        available_days = _normalize_available_days(params.get("available_days"))
        return planning_service.build_plan(
            db,
            goal_type=str(params.get("goal_type") or ""),
            distance=str(params.get("distance") or ""),
            event_date=str(params.get("event_date") or ""),
            available_hours=float(params.get("available_hours") or 10.0),
            available_days=available_days,
            demand=params.get("demand"),
            persist=True,
        )

    if action == "adjust_plan":
        if params.get("preview_fingerprint") and params.get("base_checkpoint_id") is not None:
            return planning_service.confirm_weekly_rebalance(
                db,
                base_checkpoint_id=int(params.get("base_checkpoint_id")),
                preview_fingerprint=str(params.get("preview_fingerprint")),
                weeks=int(params.get("weeks") or 1),
                as_of=params.get("as_of"),
            )
        rows = params.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError("proposal adjustment rows are invalid")
        return planning_service.apply_adjustment(
            db,
            rows=rows,
            weeks=int(params.get("weeks") or 1),
            persist=True,
        )

    if action == "recovery_replan":
        return _apply_recovery_replan_proposal(db, proposal, params, variant_kind)

    if action in {
        "create_plan_constraint",
        "retract_plan_constraint",
        "repair_plan_day",
    }:
        fingerprint = str(
            params.get("preview_fingerprint")
            or (proposal.get("preview") or {}).get("preview_fingerprint")
            or ""
        )
        return planning_service.confirm_coach_constraint_mutation(
            db,
            action=str(action),
            params=params,
            preview_fingerprint=fingerprint,
        )

    raise ValueError(f"unsupported proposal action: {action}")


def _normalize_available_days(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        days = [part.strip().lower() for part in value.split(",") if part.strip()]
        return days or None
    if isinstance(value, list):
        days = [str(part).strip().lower() for part in value if str(part).strip()]
        return days or None
    return None

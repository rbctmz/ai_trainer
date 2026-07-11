"""Headless orchestration for the auditable Recovery Replan loop."""
from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any

from api.readiness_conflicts import build_readiness_conflict_report
from data.database import Database
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from models.recovery_replan import build_recovery_replan_variant


def _outcome(report: dict[str, Any]) -> str:
    if report.get("data_gap"):
        return "data_gap"
    if report.get("silence") or not report.get("conflicts"):
        return "silence"
    return "conflict"


def _fingerprint(report: dict[str, Any], checkpoint_id: Any) -> str:
    payload = {
        "as_of": report.get("as_of"),
        "checkpoint_id": checkpoint_id,
        "readiness": report.get("readiness"),
        "horizon_days": report.get("horizon_days"),
        "conflicts": report.get("conflicts") or [],
        "data_gap": bool(report.get("data_gap")),
        "silence": bool(report.get("silence")),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _proposal_payload(
    variant: dict[str, Any],
    *,
    base_checkpoint_id: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    draft_rows = [
        {
            "index": int(row.get("index", -1)),
            "session_role": row.get("session_role"),
            "sport": row.get("sport"),
            "total_tss": row.get("total_tss"),
        }
        for row in variant.get("draft_rows") or []
        if int(row.get("index", -1)) >= 0
    ]
    params = {
        "base_checkpoint_id": int(base_checkpoint_id),
        "horizon_days": int(variant["horizon_days"]),
        "post_edit_strategy": str(variant["post_edit_strategy"]),
        "draft_rows": draft_rows,
        "selected_conflict": dict(variant["selected_conflict"]),
        "as_of": variant.get("as_of"),
    }
    preview = {
        "reason": variant.get("reason"),
        "severity": variant["selected_conflict"].get("severity"),
        "current_session": dict(variant["current_session"]),
        "recommended_session": dict(variant["recommended_session"]),
        "total_delta_tss": variant["draft_summary"].get("total_delta_tss"),
        "changed_day_count": variant["draft_summary"].get("changed_day_count"),
        "options": list(variant["options"]),
        "evidence": list(variant.get("evidence") or []),
        "lookahead_policy": variant.get("lookahead_policy"),
    }
    return params, preview


def run_recovery_replan_loop(
    db: Database,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Evaluate, audit, and optionally create one idempotent recovery proposal."""
    today = today or datetime.now().date()
    report = build_readiness_conflict_report(db)
    outcome = _outcome(report)
    checkpoint = db.get_latest_planning_checkpoint()
    checkpoint_id = checkpoint.get("id") if isinstance(checkpoint, dict) else None
    fingerprint = _fingerprint(report, checkpoint_id)
    saved = db.save_recovery_decision(
        fingerprint=fingerprint,
        outcome=outcome,
        reason=str(report.get("reason") or outcome),
        report=report,
        plan_checkpoint_id=checkpoint_id,
        date=f"{str(report.get('as_of') or today.isoformat())[:10]}T00:00:00",
    )
    decision = saved["decision"]
    proposal = None
    proposal_gap = None

    if outcome == "conflict":
        goal_plan = restore_goal_plan_from_checkpoint(checkpoint)
        variant = build_recovery_replan_variant(goal_plan, report, today=today)
        if variant is None or checkpoint_id is None:
            proposal_gap = "conflict session is not addressable in the active plan"
        else:
            params, preview = _proposal_payload(
                variant,
                base_checkpoint_id=int(checkpoint_id),
            )
            proposal = db.save_coach_proposal(
                action="recovery_replan",
                params=params,
                preview=preview,
                source="recovery_replan",
                source_key=fingerprint,
                date=f"{str(report.get('as_of') or today.isoformat())[:10]}T00:00:00",
            )
            decision = db.link_recovery_decision_proposal(decision["id"], proposal["id"])

    return {
        "outcome": outcome,
        "decision": decision,
        "proposal": proposal,
        "proposal_gap": proposal_gap,
        "readiness_conflicts": report,
    }


__all__ = ["run_recovery_replan_loop"]

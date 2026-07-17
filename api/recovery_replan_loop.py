"""Headless orchestration for the auditable Recovery Replan loop."""
from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any

from api.readiness_conflicts import build_readiness_conflict_report
from api.session_quality_forecast import record_shadow_session_quality_forecast
from data.database import Database
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from models.recovery_replan import build_recovery_replan_variant
from models.recovery_transfer import build_transfer_variant, rank_transfer_candidates

# Maps a v1 `options[]` entry's `key` onto its typed `variants[]` `kind`
# (Issue #209 M3: `variants = [keep, downgrade_today, transfer_1_3d?]`).
_VARIANT_KIND_BY_OPTION_KEY = {"keep": "keep", "recommended": "downgrade_today"}


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


def _active_proposal_key(
    report: dict[str, Any],
    variant: dict[str, Any],
    checkpoint_id: int,
) -> str:
    conflict = dict(variant.get("selected_conflict") or {})
    target_date = str(conflict.get("date") or "")[:10]
    target_row = next(
        (
            row
            for row in (variant.get("draft_rows") or [])
            if str(row.get("date") or "")[:10] == target_date
        ),
        None,
    )
    if target_row is None:
        raise ValueError("recovery proposal target row is missing")
    payload = {
        "as_of": str(report.get("as_of") or "")[:10],
        "checkpoint_id": int(checkpoint_id),
        "target_date": target_date,
        "target_index": int(target_row.get("index", -1)),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return f"recovery_replan:{sha256(canonical.encode('utf-8')).hexdigest()}"


def _resolve_transfer_session_id(
    goal_plan: dict[str, Any],
    conflict: dict[str, Any],
) -> str | None:
    """Finds the `session_id` the readiness conflict is actually referring to.

    The readiness report never carries a `session_id` (Issue #209 M3): it
    only claims a date and a role. The active plan may have moved on since
    the report was built (a prior downgrade already applied), so the match
    is fail-closed on role — a mismatch means the transfer variant is
    omitted while `keep`/`downgrade_today` (which use the report's claimed
    role directly, per v1) stay unaffected.
    """
    conflict_date = str(conflict.get("date") or "")[:10]
    claimed_role = str((conflict.get("session") or {}).get("role") or "").strip().lower()
    for template in list(goal_plan.get("session_templates") or []):
        if not isinstance(template, dict) or str(template.get("date") or "")[:10] != conflict_date:
            continue
        for session in list(template.get("sessions") or []):
            if not isinstance(session, dict):
                continue
            if str(session.get("session_role") or "").strip().lower() == claimed_role:
                session_id = str(session.get("session_id") or "").strip()
                return session_id or None
        return None
    return None


def _typed_variants(
    variant: dict[str, Any],
    transfer_variant: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    typed: list[dict[str, Any]] = []
    for option in variant.get("options") or []:
        kind = _VARIANT_KIND_BY_OPTION_KEY.get(str(option.get("key")))
        if kind is None:
            continue
        entry = dict(option)
        entry["kind"] = kind
        entry.pop("recommended", None)
        typed.append(entry)
    if transfer_variant is not None:
        typed.append(dict(transfer_variant))

    recommended_kind = "transfer_1_3d" if transfer_variant is not None else "downgrade_today"
    for entry in typed:
        if entry["kind"] == recommended_kind:
            entry["recommended"] = True
    return typed


def _proposal_payload(
    variant: dict[str, Any],
    *,
    base_checkpoint_id: int,
    transfer_variant: dict[str, Any] | None,
    transfer_candidates: list[dict[str, Any]],
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
        "variants": _typed_variants(variant, transfer_variant),
        "transfer_candidates": list(transfer_candidates),
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
            transfer_variant = None
            transfer_candidates: list[dict[str, Any]] = []
            resolved_session_id = _resolve_transfer_session_id(
                goal_plan, variant["selected_conflict"]
            )
            if resolved_session_id:
                transfer_conflict = {**variant["selected_conflict"], "session_id": resolved_session_id}
                try:
                    transfer_candidates = rank_transfer_candidates(
                        goal_plan, transfer_conflict, today=today
                    )
                    transfer_variant = build_transfer_variant(
                        goal_plan, transfer_conflict, today=today
                    )
                except ValueError:
                    # Fail-closed: a stale readiness snapshot racing a plan
                    # that already moved on must never crash the loop —
                    # keep/downgrade_today stay unaffected.
                    transfer_variant = None
                    transfer_candidates = []
            params, preview = _proposal_payload(
                variant,
                base_checkpoint_id=int(checkpoint_id),
                transfer_variant=transfer_variant,
                transfer_candidates=transfer_candidates,
            )
            proposal = db.save_coach_proposal(
                action="recovery_replan",
                params=params,
                preview=preview,
                source="recovery_replan",
                source_key=fingerprint,
                active_key=_active_proposal_key(report, variant, int(checkpoint_id)),
                date=f"{str(report.get('as_of') or today.isoformat())[:10]}T00:00:00",
            )
            if proposal["status"] == "pending" and proposal.get("preview") != preview:
                proposal = db.update_coach_proposal_preview(proposal["id"], preview)
            decision = db.link_recovery_decision_proposal(decision["id"], proposal["id"])

    shadow_forecast = None
    shadow_forecast_error = None
    try:
        shadow_forecast = record_shadow_session_quality_forecast(
            db,
            report=report,
            checkpoint=checkpoint,
            recovery_decision_id=decision["id"],
            today=today,
        )
    except Exception as exc:  # shadow output must never alter the decision loop
        shadow_forecast_error = str(exc)

    return {
        "outcome": outcome,
        "decision": decision,
        "proposal": proposal,
        "proposal_gap": proposal_gap,
        "readiness_conflicts": report,
        "session_quality_forecast": shadow_forecast,
        "session_quality_forecast_error": shadow_forecast_error,
    }


__all__ = ["run_recovery_replan_loop"]

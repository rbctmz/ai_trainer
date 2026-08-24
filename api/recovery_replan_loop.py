"""Headless orchestration for the auditable Recovery Replan loop."""
from __future__ import annotations

from datetime import date, datetime, timedelta
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

# Issue #209 M3 checker round 4 ("actual-hard-activity-tss-v1", see
# docs/recovery_transfer_execplan.md Decision Log): an already-executed
# activity that never went through the plan still counts as hard load for
# `recovery_spacing` purposes once its logged TSS reaches the same floor
# this feature already treats as the practical minimum for a quality/long
# occasion. This reads only already-persisted local `activities` rows
# (`Database.get_activities_between`) — no provider/live sync call.
ACTUAL_HARD_ACTIVITY_TSS_POLICY = 60.0

# `rank_transfer_candidates`'s `_actual_hard_near` checks ±1 day around each
# D+1..D+3 candidate, so an executed activity can influence eligibility from
# the source date itself out to source_date + 4.
_ACTUAL_HARD_ACTIVITY_WINDOW_BEFORE_DAYS = 1
_ACTUAL_HARD_ACTIVITY_WINDOW_AFTER_DAYS = 4


def _actual_hard_activity_dates(db: Database, *, source_date: date) -> list[str]:
    """Local evidence only: ISO dates of already-logged activities whose TSS
    meets `ACTUAL_HARD_ACTIVITY_TSS_POLICY`, within the window the ranker's
    ±1 day adjacency check can actually see around `source_date`."""
    window_start = source_date - timedelta(days=_ACTUAL_HARD_ACTIVITY_WINDOW_BEFORE_DAYS)
    window_end = source_date + timedelta(days=_ACTUAL_HARD_ACTIVITY_WINDOW_AFTER_DAYS)
    dates: set[str] = set()
    for activity in db.get_activities_between(window_start.isoformat(), window_end.isoformat()):
        if float(activity.get("tss") or 0.0) >= ACTUAL_HARD_ACTIVITY_TSS_POLICY:
            activity_date = str(activity.get("date") or "")[:10]
            if activity_date:
                dates.add(activity_date)
    return sorted(dates)


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

    Modern fatigue-aware reports carry the stable identity of the exact
    child session that made a multi-session day salient (#315). That identity
    is authoritative and fail-closed: if the child disappeared or its claimed
    role/sport drifted, omit the transfer rather than fall back to the primary
    session. Legacy reports still match the exact (role, sport_label) pair
    with uniqueness, preserving the Issue #209 M3 contract.
    """
    conflict_date = str(conflict.get("date") or "")[:10]
    claimed = conflict.get("session") or {}
    salience_source = claimed.get("salience_source")
    salient_session_id = (
        str(salience_source.get("session_id") or "").strip()
        if isinstance(salience_source, dict)
        else ""
    )
    claimed_role = str(claimed.get("role") or "").strip().lower()
    claimed_sport_label = str(claimed.get("sport_label") or "").strip().lower()
    for template in list(goal_plan.get("session_templates") or []):
        if not isinstance(template, dict) or str(template.get("date") or "")[:10] != conflict_date:
            continue
        sessions = [
            session
            for session in list(template.get("sessions") or [])
            if isinstance(session, dict)
        ]
        if salient_session_id:
            matches = [
                session
                for session in sessions
                if str(session.get("session_id") or "").strip()
                == salient_session_id
            ]
            if len(matches) != 1:
                return None
            salient = matches[0]
            source_role = str(salience_source.get("role") or "").strip().lower()
            source_sport_label = str(
                salience_source.get("sport_label") or ""
            ).strip().lower()
            if (
                source_role
                and str(salient.get("session_role") or "").strip().lower()
                != source_role
            ):
                return None
            if (
                source_sport_label
                and str(salient.get("sport_label") or "").strip().lower()
                != source_sport_label
            ):
                return None
            return salient_session_id
        matches = [
            session
            for session in sessions
            if str(session.get("session_role") or "").strip().lower() == claimed_role
            and str(session.get("sport_label") or "").strip().lower() == claimed_sport_label
        ]
        if len(matches) != 1:
            return None
        session_id = str(matches[0].get("session_id") or "").strip()
        return session_id or None
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
    for entry in typed:
        if entry["kind"] == "downgrade_today":
            entry["day_changes"] = list(variant.get("day_changes") or [])
    return typed


def _proposal_payload(
    variant: dict[str, Any],
    *,
    report: dict[str, Any],
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
    if variant.get("safety_guard"):
        params["safety_guard"] = dict(variant["safety_guard"])
    variants = _typed_variants(variant, transfer_variant)
    recommended_kind = next(
        entry["kind"] for entry in variants if entry.get("recommended")
    )
    selected_conflict = dict(variant["selected_conflict"])
    conflict_session = dict(selected_conflict.get("session") or {})
    day_changes = list(variant.get("day_changes") or [])
    before_sessions = (
        list((day_changes[0] or {}).get("before_sessions") or [])
        if day_changes and isinstance(day_changes[0], dict)
        else []
    )
    by_variant: dict[str, dict[str, Any]] = {}
    for entry in variants:
        kind = str(entry["kind"])
        if kind == "keep":
            by_variant[kind] = {
                "weekly_tss_delta": 0,
                "weekly_duration_delta_minutes": 0,
                "mutates_plan": False,
            }
        elif kind == "transfer_1_3d":
            by_variant[kind] = {
                "weekly_tss_delta": 0,
                "weekly_duration_delta_minutes": entry.get(
                    "weekly_duration_delta_minutes", 0
                ),
                "mutates_plan": True,
            }
        else:
            by_variant[kind] = {
                "weekly_tss_delta": variant["draft_summary"].get("total_delta_tss"),
                "weekly_duration_delta_minutes": variant["draft_summary"].get(
                    "total_delta_duration_minutes"
                ),
                "mutates_plan": True,
            }

    recommended_protection = by_variant[recommended_kind]
    preview = {
        "reason": variant.get("reason"),
        "severity": selected_conflict.get("severity"),
        "current_session": dict(variant["current_session"]),
        "recommended_session": dict(variant["recommended_session"]),
        "total_delta_tss": variant["draft_summary"].get("total_delta_tss"),
        "changed_day_count": variant["draft_summary"].get("changed_day_count"),
        "options": list(variant["options"]),
        "evidence": list(variant.get("evidence") or []),
        "lookahead_policy": variant.get("lookahead_policy"),
        "variants": variants,
        "transfer_candidates": list(transfer_candidates),
        "why_intervene": {
            "reason": variant.get("reason"),
            "severity": selected_conflict.get("severity"),
            "readiness": dict(report.get("readiness") or {}),
            "conflict": {
                "date": str(selected_conflict.get("date") or "")[:10],
                "role": conflict_session.get("role") or selected_conflict.get("role"),
                "sport_label": conflict_session.get("sport_label")
                or selected_conflict.get("sport_label"),
                "tss": conflict_session.get("tss") or selected_conflict.get("tss"),
                "day_sessions": list(before_sessions),
            },
            "evidence": list(variant.get("evidence") or []),
        },
        "what_changes": {
            "variants": variants,
            "recommended_kind": recommended_kind,
            "current_session": dict(variant["current_session"]),
            "recommended_session": dict(variant["recommended_session"]),
        },
        "what_is_protected": {
            "candidates": list(transfer_candidates),
            "weekly_tss_delta": recommended_protection["weekly_tss_delta"],
            "weekly_duration_delta_minutes": recommended_protection[
                "weekly_duration_delta_minutes"
            ],
            "by_variant": by_variant,
        },
    }
    return params, preview


def run_recovery_replan_loop(
    db: Database,
    *,
    today: date | None = None,
    decision_event_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate, audit, and optionally create one idempotent recovery proposal."""
    today = today or datetime.now().date()
    try:
        report = build_readiness_conflict_report(db, today=today)
    except TypeError as exc:
        # Compatibility for narrow test/adaptor callables that predate the
        # additive athlete-local date argument. Do not mask real TypeErrors.
        if "unexpected keyword argument 'today'" not in str(exc):
            raise
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
                conflict_source_date = date.fromisoformat(
                    str(variant["selected_conflict"].get("date") or "")[:10]
                )
                actual_hard_dates = _actual_hard_activity_dates(
                    db, source_date=conflict_source_date
                )
                try:
                    transfer_candidates = rank_transfer_candidates(
                        goal_plan,
                        transfer_conflict,
                        today=today,
                        actual_hard_dates=actual_hard_dates,
                    )
                    transfer_variant = build_transfer_variant(
                        goal_plan,
                        transfer_conflict,
                        today=today,
                        actual_hard_dates=actual_hard_dates,
                    )
                except ValueError:
                    # Fail-closed: a stale readiness snapshot racing a plan
                    # that already moved on must never crash the loop —
                    # keep/downgrade_today stay unaffected.
                    transfer_variant = None
                    transfer_candidates = []
            params, preview = _proposal_payload(
                variant,
                report=report,
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
                decision_event_id=decision_event_id,
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

"""Headless orchestration and read projections for recovery analytics."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.settings import Settings
from data.database import Database
from models.recovery_response import (
    RECOVERY_RESPONSE_RULE_VERSION,
    actual_load_bucket,
    build_episode_outcomes,
    build_recovery_analytics,
    evaluate_snapshot_eligibility,
    rpe_band,
    select_daily_anchor,
)
from services.readiness_snapshot import build_readiness_snapshot


def _fingerprint(payload: dict[str, Any]) -> str:
    frozen = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(frozen.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_post_sync_recovery_state(
    db: Database,
    *,
    capture_run_id: str,
    observed_at_utc: datetime | None = None,
    capture_mode: str = "prospective",
) -> dict[str, Any]:
    """Append one post-sync readiness fact; retrying a run is idempotent."""
    if capture_mode not in {"prospective", "backfilled"}:
        raise ValueError("capture_mode must be prospective or backfilled")
    observed = observed_at_utc or _utc_now()
    if observed.tzinfo is None:
        raise ValueError("observed_at_utc must be timezone-aware")
    timezone_name = str(Settings.ATHLETE_TIMEZONE or "")
    try:
        zone = ZoneInfo(timezone_name)
        local_date = observed.astimezone(zone).date()
    except (ZoneInfoNotFoundError, ValueError):
        local_date = observed.date()
    canonical = build_readiness_snapshot(
        db, as_of=local_date, observed_at_utc=observed
    )
    eligibility = evaluate_snapshot_eligibility(
        canonical, athlete_timezone=timezone_name
    )
    scientific_identity = {
        "capture_run_id": str(capture_run_id),
        "capture_mode": capture_mode,
    }
    payload = {
        "fingerprint": _fingerprint(scientific_identity),
        "target_key": f"readiness:{capture_mode}:{local_date.isoformat()}",
        "capture_mode": capture_mode,
        "local_date": local_date.isoformat(),
        "athlete_timezone": timezone_name,
        "observed_at_utc": canonical["observed_at_utc"],
        "capture_run_id": str(capture_run_id),
        "rule_version": canonical["rule_version"],
        "score": canonical.get("score"),
        "status": canonical.get("status") or "unknown",
        "confidence": canonical.get("confidence") or 0.0,
        "as_of_date": canonical["as_of_date"],
        "is_provisional": canonical.get("is_provisional", True),
        "source_completeness": canonical.get("source_completeness") or 0.0,
        "stale": canonical.get("stale", False),
        "eligibility_status": "eligible" if eligibility["eligible"] else "ineligible",
        "eligibility_reasons": eligibility["reasons"],
        "factors": canonical.get("factors") or [],
        "drivers": canonical.get("drivers") or [],
        "missing_inputs": canonical.get("missing_inputs") or [],
        "tsb": canonical.get("tsb") or {},
        "provenance": canonical.get("input_provenance") or {},
        "snapshot": canonical,
    }
    saved = db.save_readiness_snapshot(payload)
    try:
        episode_refresh: dict[str, Any] | None = refresh_recovery_episodes(
            db, as_of=local_date, capture_mode=capture_mode
        )
    except Exception as exc:  # source sync stays valid; derived repair is retryable
        episode_refresh = {"error": str(exc), "created": 0}
    return {
        **saved,
        "eligibility": eligibility,
        "episode_refresh": episode_refresh,
    }


def refresh_recovery_episodes(
    db: Database,
    *,
    as_of: date | None = None,
    capture_mode: str = "prospective",
) -> dict[str, Any]:
    """Materialize immutable episodes from local, source-proved evidence only."""
    resolved_as_of = as_of or datetime.now().date()
    snapshots = db.get_readiness_snapshots(capture_mode=capture_mode)
    if not snapshots:
        return {
            "as_of": resolved_as_of.isoformat(),
            "capture_mode": capture_mode,
            "created": 0,
            "episodes": len(db.get_recovery_episodes(latest_only=True, capture_mode=capture_mode)),
            "reason": "no_readiness_snapshots",
        }
    earliest = min(date.fromisoformat(str(row["local_date"])[:10]) for row in snapshots)
    lookback_days = max(1, (resolved_as_of - earliest).days + 1)
    weeks = min(12, max(1, (lookback_days + 6) // 7))

    # Local import avoids making the pure analytics module part of planning's
    # import graph and guarantees provider access is disabled.
    from api.planning_service import reconciliation_at
    from models.planning_checkpoints import restore_goal_plan_from_checkpoint
    from models.session_identity import ensure_session_identities

    reconciliation = reconciliation_at(
        db, weeks=weeks, as_of=resolved_as_of, include_provider=False
    )
    if not reconciliation.get("has_plan"):
        return {
            "as_of": resolved_as_of.isoformat(),
            "capture_mode": capture_mode,
            "created": 0,
            "episodes": len(db.get_recovery_episodes(latest_only=True, capture_mode=capture_mode)),
            "reason": "no_plan",
        }
    checkpoint = db.get_latest_planning_checkpoint()
    plan = ensure_session_identities(restore_goal_plan_from_checkpoint(checkpoint) or {})
    templates = {
        str(item.get("session_id")): dict(item)
        for item in plan.get("session_templates", []) or []
        if item.get("session_id")
    }
    start_text = earliest.isoformat()
    end_text = resolved_as_of.isoformat()
    activities = db.get_activities_between(start_text, end_text)
    matches = {
        str(row.get("target_key")): row
        for row in db.get_latest_plan_actual_matches(start_date=start_text, end_date=end_text)
    }
    feedbacks = {
        str(row.get("session_id")): row
        for row in db.get_latest_session_feedbacks(start_date=start_text, end_date=end_text)
    }
    try:
        constraints = db.get_coach_constraints(
            start_date=start_text, end_date=end_text, active_only=False, limit=500
        )
    except Exception:
        constraints = []
    exclusion_by_date: dict[str, list[str]] = {}
    for item in constraints:
        kind = str(item.get("kind") or "").lower()
        if kind in {"sick", "unavailable", "illness", "travel", "injury", "health"}:
            exclusion_by_date.setdefault(str(item.get("date") or "")[:10], []).append(kind)

    created = 0
    considered = 0
    for row in reconciliation.get("rows") or []:
        session_date = date.fromisoformat(str(row.get("date"))[:10])
        if session_date < earliest or session_date > resolved_as_of:
            continue
        if row.get("match_status") != "matched" or not row.get("actual_activity_ids"):
            continue
        considered += 1
        session_id = str(row.get("session_id") or "")
        template = templates.get(session_id, {})
        actual_tss = float(row.get("actual_total_tss") or 0.0)
        adherence = str(row.get("adherence") or "unknown")
        definition = dict(template.get("definition_snapshot") or {})
        stimulus_family = str(definition.get("step_builder_key") or "").strip() or None
        confounding_constraints = list(exclusion_by_date.get(session_date.isoformat(), []))
        reasons = ["explicit_health_or_travel_constraint"] if confounding_constraints else []
        if adherence not in {"exact", "substituted"}:
            reasons.append(adherence if adherence != "unknown" else "unknown_adherence")
        if actual_tss <= 0:
            reasons.append("missing_actual_load")
        if not stimulus_family:
            reasons.append("unversioned_stimulus")
        if template.get("kind") == "composite":
            expected_legs = len(template.get("legs") or [])
            actual_sports = {str(item.get("sport") or "") for item in row.get("actual_activities") or []}
            if expected_legs > 1 and len(actual_sports) < 2:
                reasons.append("unresolved_brick")

        pre_anchor = select_daily_anchor(
            snapshots,
            activities,
            local_date=session_date,
            athlete_timezone=str(Settings.ATHLETE_TIMEZONE),
            capture_mode=capture_mode,
        )
        if pre_anchor["snapshot"] is None:
            anchor_reason = str(pre_anchor["reason"] or "missing_pre_anchor")
            reasons.append(
                anchor_reason if anchor_reason == "activity_start_missing" else "missing_pre_anchor"
            )

        anchors: dict[int, dict[str, Any] | None] = {}
        for day_number in (1, 2, 3):
            selected = select_daily_anchor(
                snapshots,
                activities,
                local_date=session_date + timedelta(days=day_number),
                athlete_timezone=str(Settings.ATHLETE_TIMEZONE),
                capture_mode=capture_mode,
            )
            anchors[day_number] = selected["snapshot"]

        d3_elapsed = session_date + timedelta(days=3) <= resolved_as_of
        if reasons:
            status = "excluded"
        elif not d3_elapsed:
            status = "maturing"
        else:
            status = "eligible"

        outcome = (
            build_episode_outcomes(
                pre=pre_anchor["snapshot"],
                d1=anchors[1],
                d2=anchors[2],
                d3=anchors[3],
            )
            if pre_anchor["snapshot"] is not None
            else {"readiness_deltas": {"d1": None, "d2": None, "d3": None}, "recovered_by_day": None, "missing_days": [1, 2, 3]}
        )
        feedback = feedbacks.get(session_id) or {}
        match = matches.get(str(row.get("target_key"))) or {}
        frozen = {
            "target_key": f"session:{session_id}",
            "checkpoint_id": checkpoint.get("id") if checkpoint else None,
            "match_revision_id": match.get("id"),
            "feedback_id": feedback.get("id"),
            "template": template,
            "actual_activity_ids": row.get("actual_activity_ids") or [],
            "actual_activities": row.get("actual_activities") or [],
            "adherence": adherence,
            "snapshot_ids": {
                "pre": (pre_anchor["snapshot"] or {}).get("id"),
                "d1": (anchors[1] or {}).get("id"),
                "d2": (anchors[2] or {}).get("id"),
                "d3": (anchors[3] or {}).get("id"),
            },
            "outcome": outcome,
            "reasons": sorted(set(reasons)),
            "status": status,
            "capture_mode": capture_mode,
        }
        iso = session_date.isocalendar()
        saved = db.save_recovery_episode(
            {
                "fingerprint": _fingerprint(frozen),
                "target_key": f"session:{session_id}",
                "session_id": session_id,
                "plan_checkpoint_id": checkpoint.get("id") if checkpoint else None,
                "match_revision_id": match.get("id"),
                "feedback_id": feedback.get("id"),
                "session_date": session_date.isoformat(),
                "iso_week": f"{iso.year}-W{iso.week:02d}",
                "capture_mode": capture_mode,
                "status": status,
                "rule_version": RECOVERY_RESPONSE_RULE_VERSION,
                "template_id": template.get("template_key"),
                "stimulus_family": stimulus_family,
                "sport": row.get("actual_sport") or row.get("sport"),
                "role": row.get("actual_role") or row.get("role"),
                "phase": row.get("phase"),
                "actual_tss": actual_tss,
                "load_bucket": actual_load_bucket(actual_tss) if actual_tss > 0 else None,
                "adherence": adherence,
                "rpe_band": rpe_band(feedback.get("session_rpe_1_10")),
                "pre_snapshot_id": (pre_anchor["snapshot"] or {}).get("id"),
                "d1_snapshot_id": (anchors[1] or {}).get("id"),
                "d2_snapshot_id": (anchors[2] or {}).get("id"),
                "d3_snapshot_id": (anchors[3] or {}).get("id"),
                "exclusion_reasons": sorted(set(reasons)),
                "planned": {"row": row, "template": template},
                "actual": {
                    "activity_ids": row.get("actual_activity_ids") or [],
                    "activities": row.get("actual_activities") or [],
                    "tss": actual_tss,
                },
                "feedback": feedback,
                "outcome": outcome,
                "confounders": {"constraints": confounding_constraints},
            }
        )
        created += int(bool(saved.get("created")))
    rows = db.get_recovery_episodes(latest_only=True, capture_mode=capture_mode)
    return {
        "as_of": resolved_as_of.isoformat(),
        "capture_mode": capture_mode,
        "created": created,
        "considered": considered,
        "episodes": len(rows),
    }


def refresh_recovery_episodes_best_effort(
    db: Database, *, as_of: date | None = None
) -> dict[str, Any]:
    """Keep a committed source fact valid when derived analytics need repair."""
    try:
        return refresh_recovery_episodes(db, as_of=as_of)
    except Exception as exc:
        return {"created": 0, "error": str(exc)}


def recovery_analytics_summary(db: Database) -> dict[str, Any]:
    episodes = db.get_recovery_episodes(latest_only=True)
    projection = build_recovery_analytics(episodes)
    snapshots = db.get_readiness_snapshots(capture_mode="prospective")
    eligible_snapshots = [
        row for row in snapshots if row.get("eligibility_status") == "eligible"
    ]
    projection.update(
        {
            "generated_at": max(
                [str(row.get("created_at")) for row in episodes + snapshots if row.get("created_at")],
                default=None,
            ),
            "snapshot_coverage": {
                "total": len(snapshots),
                "eligible": len(eligible_snapshots),
                "ineligible": len(snapshots) - len(eligible_snapshots),
                "distinct_days": len({row.get("local_date") for row in snapshots}),
            },
            "guardrails": {
                "shadow_mode": True,
                "affects_decisions": False,
                "provider_writeback": False,
                "causal_claim": False,
                "message": "Наблюдение в shadow-режиме; план и решения не изменяются.",
            },
        }
    )
    return projection


def recovery_cohort_detail(db: Database, cohort_id: str) -> dict[str, Any] | None:
    summary = recovery_analytics_summary(db)
    cohort = next(
        (row for row in summary["registry"] if row.get("cohort_id") == cohort_id),
        None,
    )
    if cohort is None:
        return None
    episodes = db.get_recovery_episodes(latest_only=True)
    included_ids = set(cohort.get("included_episode_ids") or [])
    included = [_episode_evidence(row) for row in episodes if row.get("id") in included_ids]
    excluded = [
        _episode_evidence(row) for row in episodes
        if row.get("capture_mode") != "prospective" or row.get("status") != "eligible"
    ]
    return {
        **cohort,
        "rule_version": RECOVERY_RESPONSE_RULE_VERSION,
        "included_episodes": included,
        "excluded_episodes": excluded,
        "guardrails": summary["guardrails"],
    }


def _episode_evidence(row: dict[str, Any]) -> dict[str, Any]:
    """Expose scientific categories and provenance, never athlete free text."""
    feedback = dict(row.get("feedback") or {})
    safe_feedback = {
        key: feedback.get(key)
        for key in (
            "id",
            "revision",
            "completion_status",
            "completion_pct",
            "session_rpe_1_10",
            "quality_rating_1_5",
            "source",
            "status",
            "rule_version",
        )
        if feedback.get(key) is not None
    }
    return {
        "id": row.get("id"),
        "target_key": row.get("target_key"),
        "revision": row.get("revision"),
        "session_date": row.get("session_date"),
        "status": row.get("status"),
        "stimulus_family": row.get("stimulus_family"),
        "sport": row.get("sport"),
        "load_bucket": row.get("load_bucket"),
        "adherence": row.get("adherence"),
        "rpe_band": row.get("rpe_band"),
        "outcome": row.get("outcome") or {},
        "exclusion_reasons": row.get("exclusion_reasons") or [],
        "feedback": safe_feedback,
        "created_at": row.get("created_at"),
    }

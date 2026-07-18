"""Headless orchestration and read projections for recovery analytics."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Sequence
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
    target_session_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Materialize immutable episodes from local, source-proved evidence only.

    With no `target_session_ids`, this is the ordinary "bounded_sync" scope:
    a rolling lookback capped at 12 weeks ending at `as_of` (today by
    default), the same cost every unattended post-sync refresh has always
    had. Passing one or more `target_session_ids` switches to the
    "targeted" scope (Issue #195): each session's own planned date is
    resolved from the active checkpoint and a small reconciliation probe is
    anchored on that date, so a session older than the 12-week horizon can
    still be revalidated when new match/feedback evidence for it arrives,
    without reconciling the athlete's entire history.
    """
    if target_session_ids:
        return _refresh_targeted_episodes(
            db,
            as_of=as_of,
            capture_mode=capture_mode,
            target_session_ids=target_session_ids,
        )
    return _refresh_bounded_sync_episodes(db, as_of=as_of, capture_mode=capture_mode)


def _refresh_bounded_sync_episodes(
    db: Database,
    *,
    as_of: date | None = None,
    capture_mode: str = "prospective",
) -> dict[str, Any]:
    resolved_as_of = as_of or datetime.now().date()
    snapshots = db.get_readiness_snapshots(capture_mode=capture_mode)
    if not snapshots:
        return {
            "scope": "bounded_sync",
            "as_of": resolved_as_of.isoformat(),
            "capture_mode": capture_mode,
            "created": 0,
            "episodes": len(db.get_recovery_episodes(latest_only=True, capture_mode=capture_mode)),
            "reason": "no_readiness_snapshots",
        }
    earliest = min(date.fromisoformat(str(row["local_date"])[:10]) for row in snapshots)
    lookback_days = max(1, (resolved_as_of - earliest).days + 1)
    weeks = min(12, max(1, (lookback_days + 6) // 7))

    # Local import keeps this pure analytics module's always-loaded surface
    # small; include_provider=False below still guarantees provider access
    # stays disabled regardless of import timing.
    from models.planning_checkpoints import restore_goal_plan_from_checkpoint
    from models.session_identity import ensure_session_identities
    from services.reconciliation import reconciliation_at

    reconciliation = reconciliation_at(
        db, weeks=weeks, as_of=resolved_as_of, include_provider=False
    )
    if not reconciliation.get("has_plan"):
        return {
            "scope": "bounded_sync",
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
        saved = _materialize_matched_row(
            db,
            row,
            checkpoint=checkpoint,
            templates=templates,
            snapshots=snapshots,
            activities=activities,
            matches=matches,
            feedbacks=feedbacks,
            exclusion_by_date=exclusion_by_date,
            capture_mode=capture_mode,
            resolved_as_of=resolved_as_of,
        )
        if saved is None:
            continue
        considered += 1
        created += int(bool(saved.get("created")))
    rows = db.get_recovery_episodes(latest_only=True, capture_mode=capture_mode)
    return {
        "scope": "bounded_sync",
        "as_of": resolved_as_of.isoformat(),
        "capture_mode": capture_mode,
        "created": created,
        "considered": considered,
        "episodes": len(rows),
    }


def _materialize_matched_row(
    db: Database,
    row: dict[str, Any],
    *,
    checkpoint: dict[str, Any] | None,
    templates: dict[str, dict[str, Any]],
    snapshots: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    matches: dict[str, dict[str, Any]],
    feedbacks: dict[str, dict[str, Any]],
    exclusion_by_date: dict[str, list[str]],
    capture_mode: str,
    resolved_as_of: date,
) -> dict[str, Any] | None:
    """Append one recovery-episode revision for a matched planned session.

    Returns `None` (no DB write) when the row is not eligible for
    materialization -- not user/auto-matched, or no confirmed actual
    activities -- which the bounded-sync loop treats as "skip" and the
    targeted refresh reports as `status: "not_matched"`. Shared verbatim by
    both scopes so they can never produce subtly different episode content
    for the same evidence.
    """
    if row.get("match_status") != "matched" or not row.get("actual_activity_ids"):
        return None
    session_date = date.fromisoformat(str(row.get("date"))[:10])
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
    return db.save_recovery_episode(
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


def _refresh_targeted_episodes(
    db: Database,
    *,
    as_of: date | None,
    capture_mode: str,
    target_session_ids: Sequence[str],
) -> dict[str, Any]:
    """Materialize exactly the requested sessions via a bounded per-session probe.

    Each id resolves its own planned date from the active checkpoint, then a
    `reconciliation_at(weeks=1, as_of=<that date>, include_provider=False)`
    probe anchored on that date (never on `as_of`/today, never the full
    history) is used to (re)materialize just that one session -- so a
    session far outside the ordinary 12-week sync horizon can still be
    repaired when new match/feedback evidence for it arrives. Unknown ids,
    ids absent from the active checkpoint, and dates after `as_of` fail
    closed per-target with a machine-readable reason; they never fall back
    to a broader reconciliation.
    """
    from models.plan_actual_reconciliation import find_planned_session
    from models.planning_checkpoints import restore_goal_plan_from_checkpoint
    from models.session_identity import ensure_session_identities
    from services.reconciliation import reconciliation_at

    resolved_as_of = as_of or datetime.now().date()
    seen: set[str] = set()
    ordered_ids: list[str] = []
    for raw in target_session_ids or []:
        session_id = str(raw or "").strip()
        if not session_id or session_id in seen:
            continue
        seen.add(session_id)
        ordered_ids.append(session_id)

    checkpoint = db.get_latest_planning_checkpoint()
    plan = ensure_session_identities(restore_goal_plan_from_checkpoint(checkpoint) or {}) if checkpoint else {}
    session_templates = plan.get("session_templates", []) or []
    templates = {
        str(item.get("session_id")): dict(item)
        for item in session_templates
        if item.get("session_id")
    }

    snapshots = db.get_readiness_snapshots(capture_mode=capture_mode)
    try:
        constraints = db.get_coach_constraints(active_only=False, limit=2000)
    except Exception:
        constraints = []
    exclusion_by_date: dict[str, list[str]] = {}
    for item in constraints:
        kind = str(item.get("kind") or "").lower()
        if kind in {"sick", "unavailable", "illness", "travel", "injury", "health"}:
            exclusion_by_date.setdefault(str(item.get("date") or "")[:10], []).append(kind)

    reconciliation_cache: dict[str, dict[str, Any]] = {}
    activities_cache: dict[str, list[dict[str, Any]]] = {}
    matches_cache: dict[str, dict[str, dict[str, Any]]] = {}

    processed: list[dict[str, Any]] = []
    created = 0
    for session_id in ordered_ids:
        # find_planned_session resolves by the PARENT session's own content-
        # derived id inside `sessions[]`, never the day-level scalar
        # projection -- required so a session on a multi-session day
        # (Issue #205/#209) resolves correctly, not just the common
        # single-session-day case where the flat `templates` map above
        # happens to already agree with it.
        day_template, nested_session = find_planned_session(session_templates, session_id)
        session_date_text = str((day_template or {}).get("date") or "")[:10]
        session_date: date | None = None
        if day_template is not None and nested_session is not None and session_date_text:
            try:
                session_date = date.fromisoformat(session_date_text)
            except ValueError:
                session_date = None
        if session_date is None:
            processed.append(
                {
                    "session_id": session_id,
                    "status": "not_found",
                    "reason": "session_not_found_in_active_checkpoint",
                }
            )
            continue
        if session_date > resolved_as_of:
            processed.append(
                {"session_id": session_id, "status": "not_found", "reason": "target_date_after_as_of"}
            )
            continue

        date_key = session_date.isoformat()
        if date_key not in reconciliation_cache:
            reconciliation_cache[date_key] = reconciliation_at(
                db, weeks=1, as_of=session_date, include_provider=False
            )
            window_end = (session_date + timedelta(days=3)).isoformat()
            activities_cache[date_key] = db.get_activities_between(date_key, window_end)
            matches_cache[date_key] = {
                str(item.get("target_key")): item
                for item in db.get_latest_plan_actual_matches(start_date=date_key, end_date=date_key)
            }

        reconciliation = reconciliation_cache[date_key]
        row = next(
            (
                item
                for item in reconciliation.get("rows") or []
                if str(item.get("session_id") or "") == session_id
            ),
            None,
        )
        if row is None or not reconciliation.get("has_plan"):
            processed.append(
                {
                    "session_id": session_id,
                    "status": "not_found",
                    "reason": "session_not_in_reconciliation_window",
                }
            )
            continue

        feedback = db.get_latest_session_feedback(session_id) or {}
        saved = _materialize_matched_row(
            db,
            row,
            checkpoint=checkpoint,
            templates=templates,
            snapshots=snapshots,
            activities=activities_cache[date_key],
            matches=matches_cache[date_key],
            feedbacks={session_id: feedback},
            exclusion_by_date=exclusion_by_date,
            capture_mode=capture_mode,
            resolved_as_of=resolved_as_of,
        )
        if saved is None:
            processed.append({"session_id": session_id, "status": "not_matched"})
            continue
        is_created = bool(saved.get("created"))
        created += int(is_created)
        processed.append(
            {
                "session_id": session_id,
                "status": "created" if is_created else "unchanged",
                "episode_id": (saved.get("episode") or {}).get("id"),
            }
        )

    rows = db.get_recovery_episodes(latest_only=True, capture_mode=capture_mode)
    return {
        "scope": "targeted",
        "as_of": resolved_as_of.isoformat(),
        "capture_mode": capture_mode,
        "requested_session_ids": ordered_ids,
        "processed": processed,
        "not_found": [item["session_id"] for item in processed if item["status"] == "not_found"],
        "created": created,
        "episodes": len(rows),
    }


def refresh_recovery_episodes_best_effort(
    db: Database,
    *,
    as_of: date | None = None,
    target_session_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Keep a committed source fact valid when derived analytics need repair."""
    try:
        return refresh_recovery_episodes(db, as_of=as_of, target_session_ids=target_session_ids)
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

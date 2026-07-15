"""Headless plan building over the existing training_planner pipeline.

Replicates the exact sequence the Streamlit "Собрать план" button runs
(`create_weekly_tss_plan` → `apply_planning_constraints` →
`expand_weekly_to_daily_triathlon` → `build_daily_session_templates`), then
forecasts CTL/ATL/TSB with `BanisterModel.simulate_variable_load`. No training
math is reimplemented here — only orchestration + JSON shaping.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from typing import Any, Dict, List, Optional

import pandas as pd

from api.readiness_snapshot import build_readiness_snapshot
from data.database import Database
from models.banister import BanisterModel, tsb_zone
from models.coach_constraints import apply_constraints_to_goal_plan
from models.fit_export import build_steps_for_sport, generate_fit_csv
from models.plan_events import (
    build_primary_event,
    macrocycle_event,
    normalized_events,
    synchronize_goal_plan_events,
)
from models.planning_checkpoints import (
    build_planning_checkpoint,
    restore_goal_plan_from_checkpoint,
    summarize_planning_checkpoint,
    with_checkpoint_provenance,
)
from models.planning_near_term import apply_near_term_day_edits
from models.planning_summary import summarize_near_term_edit
from models.session_identity import ensure_session_identities
from models.planning_execution import (
    build_execution_plan_adjustment,
    build_execution_reconciliation_rows,
    rebuild_goal_plan_with_adjustment,
)
from models.plan_actual_reconciliation import (
    MATCH_RULE_VERSION,
    apply_weekly_rebalance_preview,
    build_reconciliation,
    build_weekly_rebalance_preview,
)
from models.planning_targets import (
    DEFAULT_DEMAND_LEVEL,
    build_weekly_target_breakdown,
    demand_options,
    demand_profile,
    normalize_demand_level,
    public_weekly_target_payload,
)
from models.signals_engine import assemble_signals
from models.tcx_activity_export import generate_tcx_activity
from models.tcx_export import generate_tcx_workout
from models.training_planner import (
    apply_race_event_overlays,
    apply_planning_constraints,
    build_daily_session_templates,
    compute_event_aware_phase_schedule,
    create_ics_from_daily,
    create_weekly_tss_plan,
    expand_weekly_to_daily_triathlon,
    flatten_daily_total,
    synchronize_microcycle_changes,
    weeks_until,
)
from models.workout_catalog import (
    CATALOG_VERSION,
    MATERIALIZER_RULE_VERSION,
    SELECTOR_RULE_VERSION,
    prepare_weekly_brick_allocations,
)

PLANNING_DEMAND_SETTING_KEY = "planning_demand_level"


class StalePlanningCheckpointError(ValueError):
    """A stored preview no longer matches the active planning checkpoint."""

# English (API) → internal Russian labels used by the planner.
GOAL_TYPE_MAP = {
    "triathlon": "Триатлон",
    "tri": "Триатлон",
    "run": "Бег",
    "running": "Бег",
    "bike": "Вело",
    "cycling": "Вело",
    "cycle": "Вело",
}
DISTANCE_MAP = {
    # triathlon
    "sprint": "Спринт",
    "olympic": "Олимпийка",
    "half": "Half (70.3)",
    "70.3": "Half (70.3)",
    "ironman": "Ironman",
    "full": "Ironman",
    # run
    "5k": "5 км",
    "10k": "10 км",
    "half_marathon": "Полумарафон",
    "marathon": "Марафон",
    "ultra": "Ультра",
    # bike
    "40k_tt": "40 км TT",
    "100k": "100 км",
    "100mi": "100 миль",
    "brevet": "200 км (бревет)",
    "stage_race": "Этапная гонка",
}
DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _internal_goal_type(value: str) -> str:
    return GOAL_TYPE_MAP.get((value or "").strip().lower(), value)


def _internal_distance(value: str) -> str:
    return DISTANCE_MAP.get((value or "").strip().lower(), value)


def _day_indices(days: Optional[List[str]]) -> List[int]:
    if not days:
        return list(range(7))
    idx = sorted({DAY_MAP[d.strip().lower()] for d in days if d.strip().lower() in DAY_MAP})
    return idx or list(range(7))


def _persisted_demand_level(db: Database) -> str:
    try:
        value = db.get_user_setting(PLANNING_DEMAND_SETTING_KEY, DEFAULT_DEMAND_LEVEL)
    except Exception:
        value = DEFAULT_DEMAND_LEVEL
    return normalize_demand_level(value)


def get_demand(db: Database) -> Dict[str, Any]:
    level = _persisted_demand_level(db)
    return {"demand": demand_profile(level), "options": demand_options()}


def set_demand(db: Database, level: str) -> Dict[str, Any]:
    normalized = normalize_demand_level(level)
    db.set_user_setting(PLANNING_DEMAND_SETTING_KEY, normalized)
    return get_demand(db)


def _metrics_from_signals(signals: dict[str, Any]) -> dict[str, Any]:
    load = signals.get("load", {}) or {}
    return {
        "ctl": round(float(load.get("ctl") or 0.0), 1),
        "atl": round(float(load.get("atl") or 0.0), 1),
        "tsb": round(float(load.get("tsb") or 0.0), 1),
        "form": load.get("form") or "Недостаточно данных",
    }


def _current_signals(db: Database) -> tuple[dict[str, Any], pd.DataFrame | None]:
    df = db.get_activities(90)
    return assemble_signals(activities_df=df), df


def _current_metrics(db: Database):
    signals, df = _current_signals(db)
    return _metrics_from_signals(signals), BanisterModel(), df


def _start_week(today: Optional[date] = None) -> date:
    today = today or datetime.now().date()
    return today - timedelta(days=today.weekday())  # Monday of current week


def _goal_plan_date_bounds(goal_plan: Dict[str, Any]) -> tuple[str | None, str | None]:
    dates: list[str] = []
    for item in list(goal_plan.get("daily_plan") or []):
        if not isinstance(item, (list, tuple)) or not item:
            continue
        value = item[0]
        if hasattr(value, "date"):
            dates.append(value.date().isoformat())
        elif hasattr(value, "isoformat") and not isinstance(value, str):
            dates.append(str(value.isoformat())[:10])
        else:
            text = str(value or "").strip()
            if text:
                dates.append(text[:10])
    if not dates:
        return None, None
    return min(dates), max(dates)


def _apply_active_coach_constraints(
    db: Database,
    goal_plan: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    start_date, end_date = _goal_plan_date_bounds(goal_plan)
    if not start_date or not end_date:
        return goal_plan, {"applied_count": 0, "protected_dates": [], "constraints": []}

    constraints = db.get_coach_constraints(
        start_date=start_date,
        end_date=end_date,
        active_only=True,
        limit=500,
    )
    return apply_constraints_to_goal_plan(goal_plan, constraints)


def current_status(db: Database) -> Dict[str, Any]:
    signals, _df = _current_signals(db)
    metrics = _metrics_from_signals(signals)
    checkpoint = summarize_planning_checkpoint(db.get_latest_planning_checkpoint())
    today = datetime.now().date()
    active_constraints = db.get_coach_constraints(
        start_date=today.isoformat(),
        end_date=(today + timedelta(days=30)).isoformat(),
        active_only=True,
        limit=100,
    )
    return {
        "metrics": {
            "ctl": round(float(metrics.get("ctl") or 0.0), 1),
            "atl": round(float(metrics.get("atl") or 0.0), 1),
            "tsb": round(float(metrics.get("tsb") or 0.0), 1),
            "form": metrics.get("form", "Недостаточно данных"),
        },
        "readiness_snapshot": build_readiness_snapshot(db),
        "signals": signals,
        "active_constraint_count": len(active_constraints),
        "active_constraints": active_constraints,
        "has_plan": checkpoint is not None,
        "checkpoint": checkpoint,
        "demand": demand_profile(_persisted_demand_level(db)),
        "demand_options": demand_options(),
    }


def target_preview(
    db: Database,
    *,
    goal_type: str,
    distance: str,
    available_hours: float,
    available_days: Optional[List[str]] = None,
    demand: Optional[str] = None,
) -> Dict[str, Any]:
    _metrics, _banister, activities_df = _current_metrics(db)
    gt = _internal_goal_type(goal_type)
    dist = _internal_distance(distance)
    day_indices = _day_indices(available_days)
    demand_level = normalize_demand_level(demand or _persisted_demand_level(db))
    breakdown = build_weekly_target_breakdown(
        goal_type=gt,
        distance=dist,
        activities_df=activities_df,
        available_hours=available_hours,
        available_day_indices=day_indices,
        demand=demand_level,
    )
    return {
        "goal": {"goal_type": gt, "distance": dist},
        "weekly_target": public_weekly_target_payload(breakdown),
        "breakdown": {
            "rows": list(breakdown.get("rows", []) or []),
            "availability": dict(breakdown.get("availability", {}) or {}),
            "recent_load": dict(breakdown.get("recent_load", {}) or {}),
        },
        "demand": dict(breakdown.get("demand", {}) or {}),
        "options": demand_options(),
    }


def build_plan(
    db: Database,
    *,
    goal_type: str,
    distance: str,
    event_date: str | None,
    available_hours: float,
    available_days: Optional[List[str]] = None,
    demand: Optional[str] = None,
    persist: bool = True,
    planning_mode: str = "event_goal",
    intent: str = "develop",
    focus: str = "balanced_triathlon",
    horizon_weeks: int = 8,
    manual_phases: Optional[List[str]] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    expected_base_checkpoint_id: int | None = None,
) -> Dict[str, Any]:
    metrics, banister, activities_df = _current_metrics(db)
    gt = _internal_goal_type(goal_type)
    dist = _internal_distance(distance)
    day_indices = _day_indices(available_days)

    start_week = _start_week()
    mode = str(planning_mode or "event_goal").strip().lower()
    normalized_intent = str(intent or "develop").strip().lower()
    if mode not in {"event_goal", "training_goal", "manual"}:
        raise ValueError("planning_mode must be event_goal, training_goal, or manual")
    if normalized_intent not in {"maintain", "develop"}:
        raise ValueError("intent must be maintain or develop")

    latest_checkpoint = db.get_latest_planning_checkpoint()
    latest_checkpoint_id = (
        int(latest_checkpoint.get("id"))
        if isinstance(latest_checkpoint, dict) and latest_checkpoint.get("id") is not None
        else 0
    )
    if expected_base_checkpoint_id is not None and latest_checkpoint_id != int(expected_base_checkpoint_id):
        raise StalePlanningCheckpointError(
            f"active checkpoint #{latest_checkpoint_id or 'none'} no longer matches preview base "
            f"#{int(expected_base_checkpoint_id) or 'none'}"
        )

    plan_events = normalized_events(events)
    if not plan_events and event_date:
        legacy_explicit = build_primary_event(event_date, f"{gt} {dist}")
        if legacy_explicit is not None:
            plan_events = [
                {
                    **legacy_explicit,
                    "source": "user",
                    "priority_provenance": "explicit_user",
                    "confirmed": True,
                    "requires_confirmation": False,
                }
            ]

    anchor = macrocycle_event(plan_events) if mode == "event_goal" else None
    if mode == "event_goal" and anchor is None:
        raise ValueError("event_goal requires a confirmed A event")
    goal_dt = date.fromisoformat(anchor["date"]) if anchor is not None else None
    weeks_to_race = max(1, weeks_until(goal_dt, from_date=start_week)) if goal_dt else None
    weeks_total = int(weeks_to_race or max(4, min(8, int(horizon_weeks or 8))))

    start_weekly_tss_guess = int(float(metrics.get("ctl", 50) or 50) * 7)
    demand_level = normalize_demand_level(demand or _persisted_demand_level(db))
    if demand is not None and persist:
        db.set_user_setting(PLANNING_DEMAND_SETTING_KEY, demand_level)
    target_breakdown = build_weekly_target_breakdown(
        goal_type=gt,
        distance=dist,
        activities_df=activities_df,
        available_hours=available_hours,
        available_day_indices=day_indices,
        demand=demand_level,
    )
    target_weekly_tss = int(target_breakdown.get("final_target_weekly_tss") or 0)

    base_weekly = create_weekly_tss_plan(
        start_weekly_tss=start_weekly_tss_guess,
        weeks_total=weeks_total,
        target_weekly_tss=target_weekly_tss,
        deload_every=4,
        taper_weeks=2 if mode == "event_goal" else 0,
        max_ramp=0.10,
    )
    phases = compute_event_aware_phase_schedule(
        weeks_total,
        planning_mode=mode,
        intent=normalized_intent,
        manual_phases=manual_phases,
    )

    mix_overrides: Optional[Dict[str, Dict[str, float]]] = None
    if gt == "Бег":
        mix_overrides = {p: {"run": 1.0, "bike": 0.0, "swim": 0.0} for p in phases}
    elif gt == "Вело":
        mix_overrides = {p: {"run": 0.0, "bike": 1.0, "swim": 0.0} for p in phases}

    weekly_tss_plan, constraint_details, constraint_summary = apply_planning_constraints(
        base_weekly,
        phases,
        gt,
        available_hours=available_hours,
        available_day_indices=day_indices,
        current_tsb=float(metrics.get("tsb") or 0.0),
        current_ctl=float(metrics.get("ctl") or 0.0),
        current_atl=float(metrics.get("atl") or 0.0),
    )

    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        weekly_tss_plan,
        phases,
        dist,
        start_week,
        mix_overrides=mix_overrides,
        available_day_indices=day_indices,
        goal_type=gt,
        load_state=str(constraint_summary.get("load_state", "balanced")),
    )
    for week_row, detail in zip(weekly_summary, constraint_details):
        week_row["capacity_tss"] = detail.get("capacity_tss")
        week_row["adjustment_note"] = detail.get("adjustment_note", "—")

    daily_plan, weekly_summary, event_overlay = apply_race_event_overlays(
        daily_plan,
        weekly_summary,
        plan_events,
        goal_type=gt,
        load_state=str(constraint_summary.get("load_state", "balanced")),
        as_of=datetime.now().date(),
    )
    weekly_tss_plan = [int(row.get("weekly_tss") or 0) for row in weekly_summary]

    protected_dates = set(event_overlay.get("protected_dates") or [])
    brick_allocation = prepare_weekly_brick_allocations(
        daily_plan,
        weekly_summary,
        goal_type=gt,
        protected_dates=protected_dates,
        load_state=str(constraint_summary.get("load_state", "balanced")),
    )
    daily_plan = list(brick_allocation.get("daily_plan") or daily_plan)
    athlete_profile = db.get_athlete_profile() or {}

    session_templates = build_daily_session_templates(
        daily_plan,
        weekly_summary,
        goal_type=gt,
        distance=dist,
        load_state=str(constraint_summary.get("load_state", "balanced")),
        zone_snapshot={
            "ftp": athlete_profile.get("ftp"),
            "lthr": athlete_profile.get("lthr"),
        },
        brick_day_indices=set(brick_allocation.get("brick_day_indices") or []),
    )
    event_by_date = {str(event.get("date")): event for event in plan_events}
    for template in session_templates:
        template_date = str(template.get("date") or "")
        if template_date in protected_dates:
            template["protected_by_event"] = True
        if template_date in event_by_date:
            event = event_by_date[template_date]
            for key in (
                "definition_snapshot",
                "parameter_snapshot",
                "materialized_steps",
                "target_provenance",
                "selection_evidence",
                "prescription_fingerprint",
                "legs",
                "transition_minutes",
            ):
                template.pop(key, None)
            template.update(
                {
                    "session_role": "race",
                    "session_focus": f"Старт {event['priority']} · {event.get('label') or ''}".rstrip(" ·"),
                    "sport": "off",
                    "sport_label": "старт",
                    "duration_minutes": 0,
                    "export_name": str(event.get("label") or f"Старт {event['priority']}"),
                    "is_race_event": True,
                    "race_event": dict(event),
                    "protected_by_event": True,
                    "kind": "event",
                    "template_key": f"race_event:{event['priority']}",
                    "materialization_status": "race_event",
                }
            )

    microcycle_changes = synchronize_microcycle_changes(
        event_overlay["microcycle_changes"],
        daily_plan,
        session_templates,
    )

    goal_plan = synchronize_goal_plan_events({
        "goal_type": gt,
        "distance": dist,
        "planning_mode": mode,
        "planning_intent": normalized_intent,
        "planning_focus": str(focus or "balanced_triathlon"),
        "event_date": goal_dt.isoformat() if goal_dt else "",
        "macrocycle_event_date": goal_dt.isoformat() if goal_dt else "",
        "events": plan_events,
        "weeks_to_race": weeks_to_race,
        "horizon_weeks": weeks_total,
        "start_week": start_week,
        "weekly_tss_plan": weekly_tss_plan,
        "base_weekly_tss_plan": base_weekly,
        "phases": phases,
        "daily_plan": daily_plan,
        "session_templates": session_templates,
        "catalog_version": CATALOG_VERSION,
        "selector_rule_version": SELECTOR_RULE_VERSION,
        "materializer_rule_version": MATERIALIZER_RULE_VERSION,
        "brick_allocation": {
            "status": brick_allocation.get("status"),
            "brick_day_indices": list(brick_allocation.get("brick_day_indices") or []),
            "reason": brick_allocation.get("reason"),
            "evidence": dict(brick_allocation.get("evidence") or {}),
        },
        "weekly_summary": weekly_summary,
        "overlay_rule_version": event_overlay["rule_version"],
        "event_overlays": event_overlay["overlays"],
        "microcycle_changes": microcycle_changes,
        "protected_dates": event_overlay["protected_dates"],
        "constraint_summary": constraint_summary,
        "demand_level": demand_level,
        "demand_multiplier": float(target_breakdown["demand"]["multiplier"]),
        "weekly_target_breakdown": target_breakdown,
        "planner_mix": mix_overrides,
        "planner_weights": None,
        "plan_revision": datetime.now().isoformat(),
        "near_term_edit_version": 0,
        "near_term_edit_rollback_target_checkpoint_id": None,
    })
    goal_plan, constraint_application = _apply_active_coach_constraints(db, goal_plan)
    goal_plan["microcycle_changes"] = synchronize_microcycle_changes(
        list(goal_plan.get("microcycle_changes") or []),
        list(goal_plan.get("daily_plan") or []),
        list(goal_plan.get("session_templates") or []),
    )
    event_overlay = {
        **event_overlay,
        "microcycle_changes": list(goal_plan["microcycle_changes"]),
    }
    goal_plan = synchronize_goal_plan_events(goal_plan)
    existing_plan = restore_goal_plan_from_checkpoint(latest_checkpoint)
    goal_plan = ensure_session_identities(goal_plan, previous_goal_plan=existing_plan)
    goal_plan = with_checkpoint_provenance(goal_plan, source="initial_plan")

    preview = _build_plan_preview(existing_plan, goal_plan)
    preview["base_checkpoint_id"] = latest_checkpoint_id

    plan_id: Optional[str] = None
    if persist:
        saved = db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))
        plan_id = str((saved or {}).get("id") or (saved or {}).get("checkpoint_id") or "")

    forecast = _forecast(banister, metrics, goal_plan.get("daily_plan", []), start_week)
    weeks = _weeks_payload(
        list(goal_plan.get("weekly_summary", []) or []),
        list(goal_plan.get("phases", []) or []),
    )
    adjusted_weekly_tss_plan = list(goal_plan.get("weekly_tss_plan", []) or [])
    total_tss = int(sum(int(w or 0) for w in adjusted_weekly_tss_plan))
    peak_tss = int(max(adjusted_weekly_tss_plan) if adjusted_weekly_tss_plan else 0)

    return {
        "plan_id": plan_id,
        "planning_mode": mode,
        "confirmation_required": not persist,
        "preview": preview,
        "goal": {
            "goal_type": gt,
            "distance": dist,
            "event_date": goal_plan["event_date"],
            "events": goal_plan["events"],
            "weeks_to_race": weeks_to_race,
            "macrocycle_event_date": goal_plan.get("macrocycle_event_date", ""),
        },
        "event_overlay": event_overlay,
        "weekly_target": {
            **public_weekly_target_payload(target_breakdown),
        },
        "totals": {"peak_tss": peak_tss, "total_tss": total_tss},
        "constraint_application": constraint_application,
        "weeks": weeks,
        "forecast": forecast,
    }


def _build_plan_preview(
    before: Dict[str, Any] | None,
    after: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a compact deterministic diff for explicit confirmation."""
    before_phases = list((before or {}).get("phases") or [])
    after_phases = list(after.get("phases") or [])
    before_weekly = [int(value or 0) for value in ((before or {}).get("weekly_tss_plan") or [])]
    after_weekly = [int(value or 0) for value in (after.get("weekly_tss_plan") or [])]
    return {
        "events_before": [dict(event) for event in ((before or {}).get("events") or [])],
        "events_after": [dict(event) for event in (after.get("events") or [])],
        "phases_before": before_phases,
        "phases_after": after_phases,
        "weekly_tss_before": before_weekly,
        "weekly_tss_after": after_weekly,
        "weekly_tss_delta": sum(after_weekly) - sum(before_weekly),
        "microcycle_changes": [dict(row) for row in (after.get("microcycle_changes") or [])],
    }


def discover_intervals_events(*, days: int = 180, today: date | None = None) -> Dict[str, Any]:
    """Read a bounded event preview without persisting or writing externally."""
    from services.intervals_icu import list_race_events

    resolved_days = max(1, min(365, int(days or 180)))
    start = today or datetime.now().date()
    end = start + timedelta(days=resolved_days)
    events = list_race_events(start, end)
    return {
        "oldest": start.isoformat(),
        "newest": end.isoformat(),
        "count": len(events),
        "events": events,
        "read_only": True,
    }


def _weeks_payload(weekly_summary: List[Dict[str, Any]], phases: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, w in enumerate(weekly_summary):
        ws = w.get("week_start")
        out.append(
            {
                "index": i,
                "week_start": ws.isoformat() if hasattr(ws, "isoformat") else str(ws),
                "phase": str(w.get("phase") or (phases[i] if i < len(phases) else "")),
                "weekly_tss": int(float(w.get("weekly_tss") or 0)),
                "capacity_tss": int(float(w.get("capacity_tss") or 0)) if w.get("capacity_tss") is not None else None,
                "bike": round(float(w.get("bike") or 0), 0),
                "run": round(float(w.get("run") or 0), 0),
                "swim": round(float(w.get("swim") or 0), 0),
                "adjustment_note": str(w.get("adjustment_note") or "—"),
            }
        )
    return out


_TSB_TONE_TO_FORECAST_MESSAGE = {
    "success": "🟢 Отличный прогноз — выход в пиковую форму.",
    "neutral": "🟡 Хорошая нагрузка для поддержания формы.",
    "warning": "🟠 Возможно накопление усталости — следите за восстановлением.",
    "danger": "🔴 Высокий риск переутомления — снизьте нагрузку.",
}


def _forecast(banister, metrics, daily_plan, start_week: date) -> Dict[str, Any]:
    daily_seq = flatten_daily_total(daily_plan)  # list[(datetime, total)]
    start_dt = datetime.combine(start_week, datetime.min.time())
    dates, ctl, atl, tsb = banister.simulate_variable_load(metrics, daily_seq, start_date=start_dt)

    points: List[Dict[str, Any]] = []
    n = len(dates)
    for i in range(n):
        # Weekly sampling + always keep the final point.
        if i % 7 == 0 or i == n - 1:
            points.append(
                {
                    "date": (dates[i].date() if hasattr(dates[i], "date") else dates[i]).isoformat(),
                    "ctl": round(float(ctl[i]), 1),
                    "atl": round(float(atl[i]), 1),
                    "tsb": round(float(tsb[i]), 1),
                }
            )

    final_tsb = round(float(tsb[-1]), 1) if tsb else 0.0
    message = _TSB_TONE_TO_FORECAST_MESSAGE[tsb_zone(final_tsb)["tone"]]

    return {"points": points, "final_tsb": final_tsb, "message": message}


# ---------------------------------------------------------------------------
# Active plan access (restored from the latest persisted checkpoint)
# ---------------------------------------------------------------------------
def get_active_plan(db: Database) -> Optional[Dict[str, Any]]:
    plan = restore_goal_plan_from_checkpoint(db.get_latest_planning_checkpoint())
    return ensure_session_identities(plan) if plan else None


def _infer_sport(parts: Any, template: Dict[str, Any] | None) -> str:
    sport = str((template or {}).get("sport") or "").strip()
    if sport and sport != "—":
        return sport
    parts = parts or {}
    if parts:
        return max(parts, key=lambda k: float(parts.get(k) or 0.0), default="bike")
    return "bike"


def plan_days(goal_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flat list of plan sessions for the export day-picker."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    templates = list(goal_plan.get("session_templates", []) or [])
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(daily_plan):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        dt, total, parts = item
        tpl = templates[i] if i < len(templates) else {}
        total_tss = int(round(float(total or 0)))
        if total_tss <= 0:
            continue  # skip rest days in the export picker
        out.append(
            {
                "index": i,
                "session_id": (tpl or {}).get("session_id"),
                "replaces_session_id": (tpl or {}).get("replaces_session_id"),
                "date": (dt.date() if hasattr(dt, "date") else dt).isoformat(),
                "sport": _infer_sport(parts, tpl),
                "sport_label": str((tpl or {}).get("sport_label") or _infer_sport(parts, tpl)),
                "tss": total_tss,
                "name": str((tpl or {}).get("export_name") or (tpl or {}).get("session_focus") or "Сессия"),
                "phase": str((tpl or {}).get("phase") or ""),
                "kind": str((tpl or {}).get("kind") or "single"),
                "catalog_version": (tpl or {}).get("catalog_version"),
                "template_key": (tpl or {}).get("template_key"),
                "template_version": (tpl or {}).get("template_version"),
                "template_name": (tpl or {}).get("template_name"),
                "stimulus": (tpl or {}).get("stimulus"),
                "fatigue_cost": list((tpl or {}).get("fatigue_cost") or []),
                "expected_recovery_hours": (tpl or {}).get("expected_recovery_hours"),
                "materialization_status": (tpl or {}).get("materialization_status"),
                "target_provenance": (tpl or {}).get("target_provenance"),
                "selection_evidence": (tpl or {}).get("selection_evidence"),
                "steps": [
                    {
                        "name": step.get("name"),
                        "intensity": step.get("intensity"),
                        "duration_seconds": step.get("duration_seconds"),
                        "target": step.get("target"),
                    }
                    for step in list((tpl or {}).get("materialized_steps") or [])
                ],
                "legs": [
                    {
                        "leg_index": leg.get("leg_index"),
                        "leg_id": leg.get("leg_id"),
                        "sport": leg.get("sport"),
                        "template_name": leg.get("template_name"),
                        "duration_minutes": leg.get("duration_minutes"),
                        "target_tss": leg.get("target_tss"),
                        "target_provenance": leg.get("target_provenance"),
                        "steps": [
                            {
                                "name": step.get("name"),
                                "intensity": step.get("intensity"),
                                "duration_seconds": step.get("duration_seconds"),
                                "target": step.get("target"),
                            }
                            for step in list(leg.get("materialized_steps") or [])
                        ],
                    }
                    for leg in list((tpl or {}).get("legs") or [])
                ],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Export (ICS calendar + single-workout TCX / FIT-CSV)
# ---------------------------------------------------------------------------
def export_ics(goal_plan: Dict[str, Any]) -> str:
    return create_ics_from_daily(
        list(goal_plan.get("daily_plan", []) or []),
        title_prefix=f"{goal_plan.get('goal_type', '')} {goal_plan.get('distance', '')}".strip(),
        session_templates=list(goal_plan.get("session_templates", []) or []),
    )


def export_workout(
    goal_plan: Dict[str, Any],
    index: int,
    fmt: str,
    leg: int | None = None,
) -> Dict[str, str]:
    """Return {filename, mimetype, content} for a single planned session."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    templates = list(goal_plan.get("session_templates", []) or [])
    if index < 0 or index >= len(daily_plan):
        raise ValueError("day index out of range")

    dt, total, parts = daily_plan[index]
    tpl = templates[index] if index < len(templates) else {}
    kind = str((tpl or {}).get("kind") or "single")
    suffix = ""
    if kind == "composite":
        if leg not in {1, 2}:
            raise ValueError("composite session requires leg=1 or leg=2")
        resolved_leg = next(
            (
                item
                for item in list((tpl or {}).get("legs") or [])
                if int(item.get("leg_index") or 0) == leg
            ),
            None,
        )
        if not resolved_leg:
            raise ValueError(f"composite session has no leg={leg}")
        sport = str(resolved_leg.get("sport") or "")
        steps = list(resolved_leg.get("materialized_steps") or [])
        suffix = f"_leg{leg}_{sport}"
    else:
        if leg is not None:
            raise ValueError("leg is only valid for composite sessions")
        sport = _infer_sport(parts, tpl)
        steps = list((tpl or {}).get("materialized_steps") or [])
        if not steps:
            steps = build_steps_for_sport(
                float(total or 0),
                sport,
                session_role=str((tpl or {}).get("session_role", "easy")),
                phase=(tpl or {}).get("phase"),
            )
    name = str(
        (tpl or {}).get("export_name")
        or f"{goal_plan.get('goal_type','')} — {dt.strftime('%Y-%m-%d')}"
    )
    stamp = dt.strftime("%Y%m%d")

    if fmt == "fit_csv":
        return {
            "filename": f"workout_{stamp}{suffix}.csv",
            "mimetype": "text/csv",
            "content": generate_fit_csv(name, sport, steps, created=dt),
        }
    if fmt == "tcx_activity":
        content = generate_tcx_activity(
            name, sport, steps, start_time=datetime.combine(dt.date(), datetime.min.time())
        )
        return {
            "filename": f"activity_{stamp}{suffix}.tcx",
            "mimetype": "application/vnd.garmin.tcx+xml",
            "content": content,
        }
    # default: structured TCX workout
    return {
        "filename": f"workout_{stamp}{suffix}.tcx",
        "mimetype": "application/vnd.garmin.tcx+xml",
        "content": generate_tcx_workout(name, sport, steps, created=dt),
    }


# ---------------------------------------------------------------------------
# Adjust mode (execution feedback → rebuilt plan)
# ---------------------------------------------------------------------------
def reconciliation(db: Database, weeks: int = 1) -> Dict[str, Any]:
    return reconciliation_at(db, weeks=weeks)


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
    resolved_weeks = max(1, min(12, int(weeks or 1)))
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


def _rebalance_protected_dates(
    db: Database,
    goal_plan: Dict[str, Any],
    *,
    as_of: date,
) -> set[str]:
    protected = {str(value)[:10] for value in goal_plan.get("protected_dates", []) or []}
    constraints = db.get_coach_constraints(
        start_date=(as_of + timedelta(days=1)).isoformat(),
        end_date=(as_of + timedelta(days=7)).isoformat(),
        active_only=True,
        limit=100,
    )
    protected.update(str(item.get("date") or "")[:10] for item in constraints)
    near_term = dict((goal_plan.get("constraint_summary") or {}).get("near_term_edit") or {})
    edited_dates = {str(value)[:10] for value in near_term.get("edited_dates", []) or []}
    protected.update(edited_dates)
    if near_term.get("is_active") and not edited_dates:
        legacy_horizon = max(0, int(near_term.get("horizon_days") or 0))
        for item in list(goal_plan.get("daily_plan") or [])[:legacy_horizon]:
            if isinstance(item, (list, tuple)) and item:
                item_date = item[0].date() if hasattr(item[0], "date") else item[0]
                protected.add(str(item_date)[:10])
    return {value for value in protected if value}


def preview_weekly_rebalance(
    db: Database,
    *,
    weeks: int = 1,
    as_of: date | str | None = None,
    include_provider: bool = True,
) -> Dict[str, Any]:
    reconciliation_payload = reconciliation_at(
        db,
        weeks=weeks,
        as_of=as_of,
        include_provider=include_provider,
    )
    if not reconciliation_payload.get("has_plan"):
        return {"has_plan": False, "reconciliation": reconciliation_payload, "preview": None}
    latest = db.get_latest_planning_checkpoint()
    goal_plan = restore_goal_plan_from_checkpoint(latest)
    assert goal_plan is not None
    resolved_as_of = _parse_as_of(as_of)
    preview = build_weekly_rebalance_preview(
        goal_plan,
        reconciliation_payload,
        as_of=resolved_as_of,
        protected_dates=_rebalance_protected_dates(db, goal_plan, as_of=resolved_as_of),
    )
    return {"has_plan": True, "reconciliation": reconciliation_payload, "preview": preview}


def confirm_weekly_rebalance(
    db: Database,
    *,
    base_checkpoint_id: int,
    preview_fingerprint: str,
    weeks: int = 1,
    as_of: date | str | None = None,
    include_provider: bool = True,
) -> Dict[str, Any]:
    latest = db.get_latest_planning_checkpoint()
    latest_id = int(latest.get("id")) if latest and latest.get("id") is not None else 0
    if latest_id != int(base_checkpoint_id):
        raise StalePlanningCheckpointError(
            f"active checkpoint #{latest_id or 'none'} no longer matches preview base #{base_checkpoint_id}"
        )
    current = preview_weekly_rebalance(
        db,
        weeks=weeks,
        as_of=as_of,
        include_provider=include_provider,
    )
    preview = dict(current.get("preview") or {})
    if preview.get("preview_fingerprint") != str(preview_fingerprint):
        raise StalePlanningCheckpointError("reconciliation evidence changed; request a fresh preview")
    if preview.get("status") != "proposal":
        raise ValueError("weekly rebalance preview has no applicable changes")
    goal_plan = restore_goal_plan_from_checkpoint(latest)
    assert goal_plan is not None
    updated = apply_weekly_rebalance_preview(goal_plan, preview)
    updated = with_checkpoint_provenance(
        updated,
        source="weekly_rebalance",
        parent_checkpoint_id=latest_id,
    )
    saved = db.save_planning_checkpoint(build_planning_checkpoint(updated))
    return {
        "plan_id": str(saved.get("id")),
        "applied_checkpoint_id": int(saved.get("id")),
        "base_checkpoint_id": latest_id,
        "checkpoint_source": "weekly_rebalance",
        "preview": preview,
    }


def record_plan_actual_match(
    db: Database,
    *,
    base_checkpoint_id: int,
    session_id: str,
    activity_ids: List[str],
    actual_role: str | None,
    action: str,
) -> Dict[str, Any]:
    latest = db.get_latest_planning_checkpoint()
    latest_id = int(latest.get("id")) if latest and latest.get("id") is not None else 0
    if latest_id != int(base_checkpoint_id):
        raise StalePlanningCheckpointError(
            f"active checkpoint #{latest_id or 'none'} no longer matches match base #{base_checkpoint_id}"
        )
    goal_plan = ensure_session_identities(restore_goal_plan_from_checkpoint(latest) or {})
    template = next(
        (item for item in goal_plan.get("session_templates", []) or [] if item.get("session_id") == session_id),
        None,
    )
    if template is None:
        raise ValueError("planned session not found")
    normalized_action = str(action or "confirm").strip().lower()
    if normalized_action not in {"confirm", "reject"}:
        raise ValueError("action must be confirm or reject")
    if normalized_action == "confirm" and not activity_ids:
        raise ValueError("confirm requires at least one activity")
    activities = db.get_activities_by_ids(activity_ids if normalized_action == "confirm" else [])
    if normalized_action == "confirm" and len(activities) != len(set(activity_ids)):
        raise ValueError("one or more activities were not found")
    session_date = str(template.get("date") or "")[:10]
    if any(str(item.get("date") or "")[:10] != session_date for item in activities):
        raise ValueError("confirmed activities must share the planned session date")
    if normalized_action == "confirm":
        requested_ids = {str(value) for value in activity_ids}
        existing_matches = db.get_latest_plan_actual_matches(
            start_date=session_date,
            end_date=session_date,
        )
        conflicting_targets = [
            str(item.get("target_key"))
            for item in existing_matches
            if item.get("target_key") != f"session:{session_id}"
            and str(item.get("match_status") or "") == "matched"
            and requested_ids.intersection(str(value) for value in item.get("actual_activity_ids", []) or [])
        ]
        if conflicting_targets:
            raise ValueError("one or more activities are already matched to another planned session")
    sports = {str(item.get("sport") or "") for item in activities if item.get("sport")}
    actual_snapshot = {
        "tss": round(sum(float(item.get("tss") or 0.0) for item in activities), 1),
        "duration_minutes": round(sum(float(item.get("duration_minutes") or 0.0) for item in activities), 1),
        "sport": next(iter(sports)) if len(sports) == 1 else "",
        "role": str(actual_role or "").strip().lower() or None,
    }
    target_key = f"session:{session_id}"
    previous = db.get_latest_plan_actual_matches(start_date=session_date, end_date=session_date)
    previous_row = next((item for item in previous if item.get("target_key") == target_key), None)
    payload = {
        "target_key": target_key,
        "session_id": session_id,
        "base_checkpoint_id": latest_id,
        "session_date": session_date,
        "match_status": "matched" if normalized_action == "confirm" else "unmatched",
        "match_method": "user_confirmed" if normalized_action == "confirm" else "user_rejected",
        "confidence": 1.0,
        "planned_snapshot": {
            "date": session_date,
            "sport": template.get("sport"),
            "role": template.get("session_role"),
            "session_id": session_id,
        },
        "actual_activity_ids": [str(item["activity_id"]) for item in activities],
        "actual_snapshot": actual_snapshot,
        "evidence": ["User explicitly confirmed activity match"] if normalized_action == "confirm" else ["User explicitly rejected candidate activity match"],
        "rule_version": MATCH_RULE_VERSION,
        "supersedes_match_id": previous_row.get("id") if previous_row else None,
    }
    fingerprint_source = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    payload["fingerprint"] = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    saved = db.save_plan_actual_match(payload)
    from services.recovery_analytics import refresh_recovery_episodes_best_effort

    refresh_recovery_episodes_best_effort(db, as_of=date.today())
    return saved


def apply_adjustment(
    db: Database,
    *,
    rows: List[Dict[str, Any]],
    weeks: int = 1,
    persist: bool = True,
) -> Dict[str, Any]:
    goal_plan = get_active_plan(db)
    if not goal_plan or not goal_plan.get("daily_plan"):
        raise ValueError("no active plan to adjust")

    previous_weekly_tss_plan = list(goal_plan.get("weekly_tss_plan", []) or [])
    previous_totals = {
        "peak_tss": int(max(previous_weekly_tss_plan) if previous_weekly_tss_plan else 0),
        "total_tss": int(sum(int(w or 0) for w in previous_weekly_tss_plan)),
    }

    adjustment = build_execution_plan_adjustment(goal_plan, rows, weeks=weeks)
    rebuilt_goal_plan = rebuild_goal_plan_with_adjustment(goal_plan, adjustment)
    rebuilt_goal_plan, constraint_application = _apply_active_coach_constraints(db, rebuilt_goal_plan)
    new_goal_plan = with_checkpoint_provenance(rebuilt_goal_plan, source="execution_adjustment")

    plan_id: Optional[str] = None
    if persist:
        saved = db.save_planning_checkpoint(build_planning_checkpoint(new_goal_plan))
        plan_id = str((saved or {}).get("id") or (saved or {}).get("checkpoint_id") or "")

    metrics, banister, _df = _current_metrics(db)
    start_week = _start_week()
    forecast = _forecast(banister, metrics, new_goal_plan.get("daily_plan", []), start_week)
    weeks_payload = _weeks_payload(
        list(new_goal_plan.get("weekly_summary", []) or []),
        list(new_goal_plan.get("phases", []) or []),
    )
    weekly_tss_plan = list(new_goal_plan.get("weekly_tss_plan", []) or [])
    return {
        "plan_id": plan_id,
        "adjustment": {
            "status": adjustment.get("status"),
            "label": adjustment.get("label"),
            "missed_sessions": adjustment.get("missed_sessions"),
            "completion_share": round(float(adjustment.get("completion_share") or 0.0), 2),
        },
        "totals": {
            "peak_tss": int(max(weekly_tss_plan) if weekly_tss_plan else 0),
            "total_tss": int(sum(int(w or 0) for w in weekly_tss_plan)),
        },
        "previous_totals": previous_totals,
        "constraint_application": constraint_application,
        "weeks": weeks_payload,
        "forecast": forecast,
    }


def apply_recovery_replan(
    db: Database,
    proposal_params: Dict[str, Any],
    *,
    persist: bool = True,
) -> Dict[str, Any]:
    """Apply one confirmed recovery draft against its exact base checkpoint."""
    if not isinstance(proposal_params, dict):
        raise ValueError("recovery proposal params are invalid")
    try:
        base_checkpoint_id = int(proposal_params.get("base_checkpoint_id"))
    except (TypeError, ValueError):
        raise ValueError("recovery proposal base checkpoint is invalid")

    latest = db.get_latest_planning_checkpoint()
    latest_id = int(latest.get("id")) if isinstance(latest, dict) and latest.get("id") else None
    if latest_id != base_checkpoint_id:
        raise StalePlanningCheckpointError(
            f"active checkpoint #{latest_id} no longer matches proposal base #{base_checkpoint_id}"
        )

    goal_plan = restore_goal_plan_from_checkpoint(latest)
    if not goal_plan or not goal_plan.get("daily_plan"):
        raise ValueError("active plan cannot be restored")
    draft_rows = proposal_params.get("draft_rows") or []
    if not isinstance(draft_rows, list) or not draft_rows:
        raise ValueError("recovery proposal draft rows are invalid")

    horizon_days = int(proposal_params.get("horizon_days") or 7)
    strategy = str(proposal_params.get("post_edit_strategy") or "protect_recovery")
    updated = apply_near_term_day_edits(
        goal_plan,
        draft_rows,
        horizon_days=horizon_days,
        post_edit_strategy=strategy,
        max_horizon_days=14,
    )
    constraint_summary = dict(updated.get("constraint_summary") or {})
    near_term_edit = dict(constraint_summary.get("near_term_edit") or {})
    selected_conflict = dict(proposal_params.get("selected_conflict") or {})
    near_term_edit.update(
        {
            "origin_kind": "recovery_replan",
            "origin_checkpoint_id": base_checkpoint_id,
            "origin_label": "Recovery Replan по salience-gate",
            "origin_description": str(selected_conflict.get("kind") or "readiness conflict"),
        }
    )
    constraint_summary["near_term_edit"] = near_term_edit
    updated["constraint_summary"] = constraint_summary
    updated["near_term_edit_rollback_target_checkpoint_id"] = base_checkpoint_id
    updated = with_checkpoint_provenance(
        updated,
        source="recovery_replan",
        parent_checkpoint_id=base_checkpoint_id,
    )

    saved = None
    plan_id = None
    if persist:
        saved = db.save_planning_checkpoint(build_planning_checkpoint(updated))
        plan_id = str((saved or {}).get("id") or "")

    weekly_tss_plan = list(updated.get("weekly_tss_plan") or [])
    summary = summarize_near_term_edit(updated.get("constraint_summary") or {}) or {}
    affected_dates = sorted(
        {str(value)[:10] for value in near_term_edit.get("edited_dates", []) or []}
    )
    return {
        "plan_id": plan_id,
        "applied_checkpoint_id": int(plan_id) if plan_id else None,
        "rollback_checkpoint_id": base_checkpoint_id,
        "checkpoint_source": "recovery_replan",
        "affected_dates": affected_dates,
        "near_term_edit": summary,
        "totals": {
            "peak_tss": int(max(weekly_tss_plan) if weekly_tss_plan else 0),
            "total_tss": int(sum(int(value or 0) for value in weekly_tss_plan)),
        },
    }


def rollback_recovery_replan(
    db: Database,
    proposal_result: Dict[str, Any],
    *,
    persist: bool = True,
) -> Dict[str, Any]:
    """Restore a recovery proposal's base as a new append-only checkpoint."""
    if not isinstance(proposal_result, dict):
        raise ValueError("recovery proposal result is invalid")
    try:
        applied_checkpoint_id = int(
            proposal_result.get("applied_checkpoint_id") or proposal_result.get("plan_id")
        )
        rollback_checkpoint_id = int(proposal_result.get("rollback_checkpoint_id"))
    except (TypeError, ValueError):
        raise ValueError("recovery rollback checkpoint ids are invalid")

    latest = db.get_latest_planning_checkpoint()
    latest_id = int(latest.get("id")) if isinstance(latest, dict) and latest.get("id") else None
    if latest_id != applied_checkpoint_id:
        raise StalePlanningCheckpointError(
            f"active checkpoint #{latest_id} no longer matches recovery checkpoint #{applied_checkpoint_id}"
        )

    rollback_checkpoint = db.get_planning_checkpoint(rollback_checkpoint_id)
    restored = restore_goal_plan_from_checkpoint(rollback_checkpoint)
    if not restored or not restored.get("daily_plan"):
        raise ValueError("recovery rollback checkpoint cannot be restored")
    restored = with_checkpoint_provenance(
        restored,
        source="restore_version",
        parent_checkpoint_id=applied_checkpoint_id,
        restored_from_checkpoint_id=rollback_checkpoint_id,
    )

    saved = None
    plan_id = None
    if persist:
        saved = db.save_planning_checkpoint(build_planning_checkpoint(restored))
        plan_id = str((saved or {}).get("id") or "")
    return {
        "plan_id": plan_id,
        "checkpoint_source": "restore_version",
        "replaced_checkpoint_id": applied_checkpoint_id,
        "restored_from_checkpoint_id": rollback_checkpoint_id,
        "affected_dates": list(proposal_result.get("affected_dates") or []),
    }


def deliver_intervals_plan(
    db: Database,
    *,
    days: int,
    today: date | None = None,
) -> Dict[str, Any]:
    """Deliver a future slice through the shared headless provider boundary."""
    from services.intervals_plan_delivery import safe_deliver_active_plan

    return safe_deliver_active_plan(
        db,
        days=days,
        today=today,
        source="manual",
    )


def planning_history(db: Database, limit: int = 10) -> Dict[str, Any]:
    checkpoints = db.get_recent_planning_checkpoints(limit=max(1, min(int(limit or 10), 50)))
    items: List[Dict[str, Any]] = []
    for checkpoint in checkpoints:
        summary = summarize_planning_checkpoint(checkpoint)
        if not summary:
            continue
        provenance = summary.get("provenance") or {}
        source = str(provenance.get("source") or "")
        plan_adjustment_label = str(summary.get("plan_adjustment_label") or "Нет")
        if source in {"execution_feedback", "execution_adjustment"}:
            item_type = "reduce" if plan_adjustment_label != "Нет" else "regenerate"
        elif source == "manual_edit":
            item_type = "swap"
        elif source == "initial_plan":
            item_type = "regenerate"
        else:
            item_type = "regenerate"
        outcome = plan_adjustment_label
        transition = summary.get("execution_weekly_review") or {}
        if isinstance(transition, dict) and transition.get("headline"):
            outcome = f"{outcome} · {transition['headline']}" if outcome != "Нет" else str(transition["headline"])
        if outcome == "Нет":
            outcome = str(summary.get("headline") or provenance.get("detail") or "План сохранён")
        items.append(
            {
                "checkpoint_id": summary.get("checkpoint_id"),
                "date": str(checkpoint.get("created_at") or ""),
                "date_label": summary.get("created_at_label") or "",
                "type": item_type,
                "type_label": {
                    "reduce": "Снижение",
                    "swap": "Замена",
                    "regenerate": "Пересборка",
                }.get(item_type, "Пересборка"),
                "source": source,
                "source_label": provenance.get("label") or "",
                "outcome_note": outcome,
                "title": summary.get("title") or "",
                "total_tss": summary.get("total_tss"),
                "peak_tss": summary.get("peak_tss"),
            }
        )
    return {"has_history": bool(items), "items": items}

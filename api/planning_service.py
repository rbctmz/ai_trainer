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
from models.planning_near_term import (
    apply_near_term_day_edits,
    rematerialize_non_executable_sessions,
)
from models.recovery_replan import assert_recovery_replan_safety
from models.planning_summary import summarize_near_term_edit
from models.session_identity import ensure_session_identities
from models.session_transfer import apply_session_transfer
from models.planning_execution import (
    build_execution_plan_adjustment,
    build_execution_reconciliation_rows,
    rebuild_goal_plan_with_adjustment,
)
from models.plan_actual_reconciliation import (
    MATCH_RULE_VERSION,
    apply_weekly_rebalance_preview,
    build_weekly_rebalance_preview,
    find_planned_session,
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
    derive_weekly_sport_buckets_from_sessions,
    expand_weekly_to_daily_triathlon,
    flatten_daily_total,
    SESSION_ROLE_LABELS_RU,
    synchronize_microcycle_changes,
    weeks_until,
)
from models.workout_catalog import (
    CATALOG_VERSION,
    MATERIALIZER_RULE_VERSION,
    SELECTOR_RULE_VERSION,
    planned_session_requires_repair,
    prepare_weekly_brick_allocations,
    require_executable_planned_session,
)
# Issue #194: reconciliation_at and its as_of/provider-evidence helpers are
# owned by the services layer (services/reconciliation.py) — they are
# orchestration logic, not an API contract. This re-export (the same
# function objects, not copies) keeps every existing
# api.planning_service.reconciliation_at caller working unchanged.
from services.reconciliation import (
    _parse_as_of,
    _provider_reconciliation_evidence,
    reconciliation_at,
)
from services.planning_contracts import (
    DAY_MAP,
    DISTANCE_MAP,
    GOAL_TYPE_MAP,
    PLANNING_INTENTS,
    PLANNING_MODES,
)
from services.planning_events import discover_intervals_events as discover_intervals_events

PLANNING_DEMAND_SETTING_KEY = "planning_demand_level"

class StalePlanningCheckpointError(ValueError):
    """A stored preview no longer matches the active planning checkpoint."""

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


def _overview_date(value: Any) -> date | None:
    """Parse a persisted date defensively for the reader-only overview."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except (TypeError, ValueError):
        return None


def _overview_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _overview_event_rows(goal_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return only stored A/B/C events; this reader path never discovers new ones."""
    rows: List[Dict[str, Any]] = []
    for item in list(goal_plan.get("events") or []):
        if not isinstance(item, dict):
            continue
        event_date = _overview_date(item.get("date"))
        priority = str(item.get("priority") or "").strip().upper()
        if event_date is None or priority not in {"A", "B", "C"}:
            continue
        rows.append(
            {
                "date": event_date.isoformat(),
                "priority": priority,
                "label": str(item.get("label") or f"Старт {priority}").strip() or f"Старт {priority}",
                "confirmed": item.get("confirmed") is not False,
            }
        )
    return rows


def _active_plan_roadmap(goal_plan: Dict[str, Any], *, today: date) -> Dict[str, Any]:
    """Build bounded, proportional phase and event data from one checkpoint."""
    weekly_rows = [
        dict(row)
        for row in list(goal_plan.get("weekly_summary") or [])
        if isinstance(row, dict) and _overview_date(row.get("week_start")) is not None
    ]
    weekly_rows.sort(key=lambda row: _overview_date(row["week_start"]) or date.max)
    if not weekly_rows:
        return {
            "state": "data_gap",
            "reason": "В checkpoint нет дат фаз плана.",
            "segments": [],
            "events": [],
            "current_marker": None,
        }

    week_starts = [_overview_date(row["week_start"]) for row in weekly_rows]
    assert all(value is not None for value in week_starts)
    starts = [value for value in week_starts if value is not None]
    horizon_start = starts[0]
    plan_end_raw = _goal_plan_date_bounds(goal_plan)[1]
    horizon_end = _overview_date(plan_end_raw) or (starts[-1] + timedelta(days=6))
    # A race can fall on the Monday immediately after the final scheduled
    # microcycle. Keep its stored marker in the reader horizon rather than
    # silently dropping a valid A/B/C event at that calendar boundary.
    stored_event_dates = [
        _overview_date(event["date"])
        for event in _overview_event_rows(goal_plan)
    ]
    horizon_end = max(
        [horizon_end, *(event_date for event_date in stored_event_dates if event_date is not None)]
    )
    if horizon_end < horizon_start:
        return {
            "state": "data_gap",
            "reason": "Границы горизонта плана некорректны.",
            "segments": [],
            "events": [],
            "current_marker": None,
        }

    weekly_rows = [
        row
        for row in weekly_rows
        if (_overview_date(row["week_start"]) or date.max) <= horizon_end
    ]
    starts = [_overview_date(row["week_start"]) for row in weekly_rows]
    starts = [value for value in starts if value is not None]
    if not starts:
        return {
            "state": "data_gap",
            "reason": "Даты фаз не входят в горизонт сохранённого плана.",
            "segments": [],
            "events": [],
            "current_marker": None,
        }

    span_days = max(1, (horizon_end - horizon_start).days)
    segments: List[Dict[str, Any]] = []
    group_start = 0
    for index in range(1, len(weekly_rows) + 1):
        previous_phase = str(weekly_rows[index - 1].get("phase") or "Не указана").strip() or "Не указана"
        next_phase = (
            str(weekly_rows[index].get("phase") or "Не указана").strip()
            if index < len(weekly_rows)
            else None
        )
        if index < len(weekly_rows) and next_phase == previous_phase:
            continue
        segment_start = starts[group_start]
        segment_end = (starts[index] - timedelta(days=1)) if index < len(starts) else horizon_end
        segment_end = min(segment_end, horizon_end)
        segments.append(
            {
                "phase": previous_phase,
                "start_date": segment_start.isoformat(),
                "end_date": segment_end.isoformat(),
                "duration_days": (segment_end - segment_start).days + 1,
                "start_percent": round(((segment_start - horizon_start).days / span_days) * 100, 2),
                "end_percent": round(((segment_end - horizon_start).days / span_days) * 100, 2),
                "is_current": segment_start <= today <= segment_end,
            }
        )
        group_start = index

    events = []
    for event in _overview_event_rows(goal_plan):
        event_date = _overview_date(event["date"])
        assert event_date is not None
        if horizon_start <= event_date <= horizon_end:
            events.append(
                {
                    **event,
                    "position_percent": round(((event_date - horizon_start).days / span_days) * 100, 2),
                }
            )
    current_marker = None
    if horizon_start <= today <= horizon_end:
        current_marker = {
            "date": today.isoformat(),
            "position_percent": round(((today - horizon_start).days / span_days) * 100, 2),
        }

    return {
        "state": "available",
        "reason": None,
        "horizon_start": horizon_start.isoformat(),
        "horizon_end": horizon_end.isoformat(),
        "segments": segments,
        "events": events,
        "current_marker": current_marker,
    }


def _sample_form_points(
    dates: List[Any],
    ctl: List[float],
    atl: List[float],
    tsb: List[float],
    *,
    required_dates: set[str] | None = None,
) -> List[Dict[str, Any]]:
    """Bound a daily Banister series to weekly points plus explicit boundaries."""
    required_dates = required_dates or set()
    points: List[Dict[str, Any]] = []
    for index, value in enumerate(dates):
        point_date = value.date() if hasattr(value, "date") else _overview_date(value)
        if point_date is None:
            continue
        iso_date = point_date.isoformat()
        if index % 7 != 0 and index != len(dates) - 1 and iso_date not in required_dates:
            continue
        points.append(
            {
                "date": iso_date,
                "ctl": round(float(ctl[index]), 1),
                "atl": round(float(atl[index]), 1),
                "tsb": round(float(tsb[index]), 1),
            }
        )
    return points


def _active_plan_form_projection(
    db: Database,
    goal_plan: Dict[str, Any],
    *,
    today: date,
    planning_mode: str,
    event: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Return actual and planned form series without provider I/O or writes."""
    activities = db.get_activities(90)
    if activities is None or activities.empty or not {"date", "tss"}.issubset(activities.columns):
        return {
            "state": "data_gap",
            "reason": "Недостаточно локальной истории нагрузок для прогноза формы.",
            "boundary_date": today.isoformat(),
            "actual_points": [],
            "forecast_points": [],
            "summary": None,
        }

    history = activities[["date", "tss"]].copy()
    history["date"] = pd.to_datetime(history["date"], errors="coerce")
    history["tss"] = pd.to_numeric(history["tss"], errors="coerce").fillna(0.0)
    history = history.dropna(subset=["date"])
    history = history[history["date"].dt.date <= today]
    if history.empty:
        return {
            "state": "data_gap",
            "reason": "Локальная история не содержит нагрузок до сегодняшней даты.",
            "boundary_date": today.isoformat(),
            "actual_points": [],
            "forecast_points": [],
            "summary": None,
        }

    daily_history = history.groupby(history["date"].dt.normalize())["tss"].sum().sort_index()
    daily_index = pd.date_range(start=daily_history.index.min(), end=pd.Timestamp(today), freq="D")
    daily_history = daily_history.reindex(daily_index, fill_value=0.0)
    banister = BanisterModel()
    actual_dates, actual_ctl, actual_atl, actual_tsb = banister.calculate_ctl_atl_tsb(
        daily_history.tolist(), daily_history.index.tolist()
    )
    if not actual_dates:
        return {
            "state": "data_gap",
            "reason": "Не удалось построить фактическую траекторию формы.",
            "boundary_date": today.isoformat(),
            "actual_points": [],
            "forecast_points": [],
            "summary": None,
        }

    future_daily = []
    for item in list(goal_plan.get("daily_plan") or []):
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            continue
        planned_date = _overview_date(item[0])
        if planned_date is None or planned_date <= today:
            continue
        try:
            planned_tss = float(item[1] or 0.0)
        except (TypeError, ValueError):
            continue
        future_daily.append((datetime.combine(planned_date, datetime.min.time()), planned_tss, {}))
    future_daily.sort(key=lambda item: item[0])
    if not future_daily:
        return {
            "state": "data_gap",
            "reason": "В checkpoint нет будущих дней плана для прогноза формы.",
            "boundary_date": today.isoformat(),
            "actual_points": [],
            "forecast_points": [],
            "summary": None,
        }

    event_date = _overview_date((event or {}).get("date"))
    target_date = event_date if planning_mode == "event_goal" and event_date else future_daily[-1][0].date()
    final_planned_date = future_daily[-1][0].date()
    # Weekly schedules can end on Sunday while the persisted race sits on the
    # following Monday. Add only that short, zero-load calendar bridge so the
    # existing forecast can include its saved race load at the real target.
    if final_planned_date < target_date <= final_planned_date + timedelta(days=7):
        for offset in range(1, (target_date - final_planned_date).days + 1):
            bridge_date = final_planned_date + timedelta(days=offset)
            future_daily.append((datetime.combine(bridge_date, datetime.min.time()), 0.0, {}))
    if target_date < future_daily[0][0].date() or target_date > future_daily[-1][0].date():
        return {
            "state": "data_gap",
            "reason": "Целевая дата не входит в сохранённый будущий горизонт плана.",
            "boundary_date": today.isoformat(),
            "actual_points": [],
            "forecast_points": [],
            "summary": None,
        }
    current_metrics = {
        "ctl": float(actual_ctl[-1]),
        "atl": float(actual_atl[-1]),
        "tsb": float(actual_tsb[-1]),
    }
    # `_forecast` owns the planner's existing Banister simulation. Requesting
    # the target date only adds a sampled point; it does not alter its formula.
    forecast = _forecast(
        banister,
        current_metrics,
        future_daily,
        future_daily[0][0].date(),
        race_forecast_loads=goal_plan.get("race_forecast_loads"),
        required_dates={target_date.isoformat()},
    )
    forecast_points = list(forecast.get("points") or [])
    target_point = next(
        (point for point in forecast_points if point.get("date") == target_date.isoformat()),
        None,
    )
    if not forecast_points or target_point is None:
        return {
            "state": "data_gap",
            "reason": "Недостаточно точек планового прогноза формы.",
            "boundary_date": today.isoformat(),
            "actual_points": [],
            "forecast_points": [],
            "summary": None,
        }

    return {
        "state": "available",
        "reason": None,
        "boundary_date": today.isoformat(),
        "actual_points": _sample_form_points(actual_dates, actual_ctl, actual_atl, actual_tsb),
        "forecast_points": forecast_points,
        "summary": {
            "current_ctl": round(float(actual_ctl[-1]), 1),
            "peak_projected_ctl": round(max(float(point["ctl"]) for point in forecast_points), 1),
            "projected_ctl": float(target_point["ctl"]),
            "projected_tsb": float(target_point["tsb"]),
            "target_date": target_date.isoformat(),
            "target_kind": "event" if planning_mode == "event_goal" and event_date else "horizon_end",
            "days_to_goal": max(0, (target_date - today).days) if planning_mode == "event_goal" and event_date else None,
        },
    }


def active_plan_overview(db: Database) -> Dict[str, Any]:
    """Project the active checkpoint into a compact, reader-facing overview.

    This is deliberately a checkpoint-only read. In particular it does not
    discover events or ask an activity provider for new execution evidence.
    """
    checkpoint = db.get_latest_planning_checkpoint()
    goal_plan = restore_goal_plan_from_checkpoint(checkpoint)
    if not checkpoint or not goal_plan:
        return {"has_plan": False}

    today = datetime.now().date()
    planning_mode = str(goal_plan.get("planning_mode") or "").strip() or "training_goal"
    events = [dict(item) for item in list(goal_plan.get("events") or []) if isinstance(item, dict)]
    confirmed_a_event = next(
        (
            item
            for item in events
            if str(item.get("priority") or "").upper() == "A"
            and item.get("confirmed") is True
        ),
        None,
    )

    event: Dict[str, Any] | None = None
    if confirmed_a_event is not None:
        event_date = _overview_date(confirmed_a_event.get("date"))
        event = {
            "label": str(confirmed_a_event.get("label") or "A-цель").strip() or "A-цель",
            "priority": "A",
            "date": event_date.isoformat() if event_date else None,
            "confirmed": True,
        }

    weekly_rows = [
        dict(row)
        for row in list(goal_plan.get("weekly_summary") or [])
        if isinstance(row, dict)
    ]
    current_index: int | None = None
    parsed_week_starts = [_overview_date(row.get("week_start")) for row in weekly_rows]
    for index, week_start in enumerate(parsed_week_starts):
        if week_start and week_start <= today < week_start + timedelta(days=7):
            current_index = index
            break
    if current_index is None:
        future_indexes = [
            index for index, week_start in enumerate(parsed_week_starts) if week_start and week_start > today
        ]
        if future_indexes:
            current_index = future_indexes[0]
        elif weekly_rows:
            current_index = len(weekly_rows) - 1

    current_week: Dict[str, Any] | None = None
    if current_index is not None:
        row = weekly_rows[current_index]
        week_start = parsed_week_starts[current_index]
        current_week = {
            "number": current_index + 1,
            "phase": str(row.get("phase") or "").strip() or None,
            "week_start": week_start.isoformat() if week_start else None,
            "weekly_tss": _overview_int(row.get("weekly_tss")),
        }

    completed_weeks = sum(
        1
        for week_start in parsed_week_starts
        if week_start is not None and week_start + timedelta(days=7) <= today
    )
    total_weeks = len(weekly_rows) or _overview_int(goal_plan.get("horizon_weeks"))
    progress_status = "completed" if total_weeks and completed_weeks >= total_weeks else "active"

    checkpoint_summary = summarize_planning_checkpoint(checkpoint) or {}
    execution_summary = checkpoint_summary.get("execution_reconciliation")
    weekly_review = checkpoint_summary.get("execution_weekly_review")
    if isinstance(execution_summary, dict):
        execution = {
            "state": "available",
            "label": str(execution_summary.get("compact_label") or "Статус выполнения доступен"),
            "description": str(execution_summary.get("description") or ""),
        }
    elif isinstance(weekly_review, dict) and weekly_review.get("headline"):
        execution = {
            "state": "available",
            "label": str(weekly_review["headline"]),
            "description": str(weekly_review.get("review_badge") or ""),
        }
    else:
        execution = {
            "state": "data_gap",
            "label": "В последнем checkpoint нет сохранённой сводки выполнения.",
            "description": "Актуальные локальные данные доступны во вкладке «Выполнение».",
        }

    goal = {
        "goal_type": str(goal_plan.get("goal_type") or "").strip() or None,
        "distance": str(goal_plan.get("distance") or "").strip() or None,
        "planning_mode": planning_mode,
        "event": event,
    }
    if planning_mode == "training_goal":
        timeline: Dict[str, Any] = {
            "kind": "rolling",
            "horizon_weeks": _overview_int(goal_plan.get("horizon_weeks") or total_weeks),
        }
    else:
        event_date = _overview_date((event or {}).get("date"))
        timeline = {
            "kind": "event",
            "event": event,
            "days_remaining": max(0, (event_date - today).days) if event_date else None,
            "weeks_remaining": max(0, (event_date - today).days // 7) if event_date else None,
        }

    roadmap = _active_plan_roadmap(goal_plan, today=today)
    form_projection = _active_plan_form_projection(
        db,
        goal_plan,
        today=today,
        planning_mode=planning_mode,
        event=event,
    )

    return {
        "has_plan": True,
        "goal": goal,
        "timeline": timeline,
        "current_week": current_week,
        "progress": {
            "completed_weeks": min(completed_weeks, total_weeks),
            "total_weeks": total_weeks,
            "status": progress_status,
            "status_label": "План завершён" if progress_status == "completed" else "Активный план",
        },
        "execution": execution,
        "roadmap": roadmap,
        "form_projection": form_projection,
        "weeks": [
            {
                "number": index + 1,
                "week_start": week_start.isoformat() if week_start else None,
                "phase": str(row.get("phase") or "").strip() or None,
                "weekly_tss": _overview_int(row.get("weekly_tss")),
            }
            for index, (row, week_start) in enumerate(zip(weekly_rows, parsed_week_starts))
        ],
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
    if mode not in PLANNING_MODES:
        raise ValueError("planning_mode must be event_goal, training_goal, or manual")
    if normalized_intent not in PLANNING_INTENTS:
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
        available_weekly_hours=float(available_hours or 0.0) or None,
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
            # The profile API/storage name pins the canonical unit. The workout
            # catalog's established input key is shorter but means the same
            # seconds-per-kilometre value.
            "threshold_pace": athlete_profile.get(
                "threshold_pace_seconds_per_km"
            ),
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
        "race_forecast_loads": list(event_overlay.get("race_forecast_loads") or []),
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
    # Issue #205: the product weekly table is a projection of the materialized
    # leaf sessions (parts → sessions → weekly), computed after constraints and
    # identity stamping so it reflects the final executable truth.
    goal_plan["weekly_summary"] = derive_weekly_sport_buckets_from_sessions(
        list(goal_plan.get("weekly_summary") or []),
        list(goal_plan.get("session_templates") or []),
    )
    goal_plan = with_checkpoint_provenance(goal_plan, source="initial_plan")

    preview = _build_plan_preview(existing_plan, goal_plan)
    preview["base_checkpoint_id"] = latest_checkpoint_id

    plan_id: Optional[str] = None
    if persist:
        saved = db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))
        plan_id = str((saved or {}).get("id") or (saved or {}).get("checkpoint_id") or "")

    forecast = _forecast(
        banister,
        metrics,
        goal_plan.get("daily_plan", []),
        start_week,
        race_forecast_loads=goal_plan.get("race_forecast_loads"),
    )
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
                # Issue #205 M6: explicit race-effort forecast for the week —
                # shown separately, never folded into weekly_tss or buckets.
                "race_forecast_tss": (
                    round(float(w.get("race_forecast_tss")), 1)
                    if w.get("race_forecast_tss") is not None
                    else None
                ),
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


def _forecast(
    banister,
    metrics,
    daily_plan,
    start_week: date,
    race_forecast_loads=None,
    required_dates: set[str] | None = None,
) -> Dict[str, Any]:
    daily_seq = flatten_daily_total(daily_plan)  # list[(datetime, total)]
    # Issue #205 M6: the load model anticipates the race effort. The forecast
    # TSS joins the simulation input only — the plan's daily totals, sessions,
    # and delivery stay untouched (the race day remains protected and empty).
    race_by_date: Dict[str, float] = {}
    for row in list(race_forecast_loads or []):
        day = str(row.get("date") or "")[:10]
        if day:
            race_by_date[day] = race_by_date.get(day, 0.0) + float(row.get("tss") or 0.0)
    if race_by_date:
        daily_seq = [
            (
                dt,
                float(total or 0.0)
                + race_by_date.get(
                    (dt.date() if hasattr(dt, "date") else dt).isoformat(), 0.0
                ),
            )
            for dt, total in daily_seq
        ]
    start_dt = datetime.combine(start_week, datetime.min.time())
    dates, ctl, atl, tsb = banister.simulate_variable_load(metrics, daily_seq, start_date=start_dt)

    points: List[Dict[str, Any]] = []
    required_dates = required_dates or set()
    n = len(dates)
    for i in range(n):
        point_date = (dates[i].date() if hasattr(dates[i], "date") else dates[i]).isoformat()
        # Weekly sampling, caller-requested target dates, and the final point.
        if i % 7 == 0 or i == n - 1 or point_date in required_dates:
            points.append(
                {
                    "date": point_date,
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


def _recovery_replan_session_ids_from_history(
    db: Database,
    latest: Dict[str, Any],
) -> set[str]:
    """Resolve recovery lineage at leaf granularity from checkpoint ancestry."""
    recovery_session_ids: set[str] = set()
    visited: set[int] = set()
    checkpoint: Dict[str, Any] | None = latest

    while checkpoint:
        try:
            checkpoint_id = int(checkpoint.get("id"))
        except (TypeError, ValueError):
            break
        if checkpoint_id in visited:
            raise ValueError("planning checkpoint ancestry contains a cycle")
        visited.add(checkpoint_id)

        plan = restore_goal_plan_from_checkpoint(checkpoint) or {}
        source = str(
            checkpoint.get("checkpoint_source")
            or plan.get("checkpoint_source")
            or ""
        ).strip()
        near_term_edit = (
            plan.get("constraint_summary", {}) or {}
        ).get("near_term_edit", {}) or {}
        if source == "recovery_replan":
            edited_dates = {
                str(value)[:10]
                for value in list(near_term_edit.get("edited_dates") or [])
                if str(value)[:10]
            }
            for template in list(plan.get("session_templates") or []):
                day = str(template.get("date") or "")[:10]
                if day not in edited_dates:
                    continue
                sessions = list(template.get("sessions") or [])
                candidates = sessions or [template]
                for session in candidates:
                    if not isinstance(session, dict):
                        continue
                    session_id = str(session.get("session_id") or "").strip()
                    if (
                        session_id
                        and str(session.get("template_key") or "").startswith("manual:")
                        and planned_session_requires_repair(session)
                    ):
                        recovery_session_ids.add(session_id)

        parent_id = plan.get("checkpoint_parent_id")
        if parent_id is None:
            parent_id = checkpoint.get("checkpoint_parent_id")
        try:
            parent_id = int(parent_id) if parent_id is not None else None
        except (TypeError, ValueError):
            raise ValueError("planning checkpoint ancestry has an invalid parent id")
        checkpoint = db.get_planning_checkpoint(parent_id) if parent_id is not None else None

    return recovery_session_ids


def repair_active_plan_materialization(
    db: Database,
    *,
    persist: bool = False,
) -> Dict[str, Any]:
    """Preview or append one checkpoint that repairs non-executable modern leaves."""
    latest = db.get_latest_planning_checkpoint()
    if not latest:
        raise ValueError("no active plan")
    base_checkpoint_id = int(latest["id"])
    goal_plan = restore_goal_plan_from_checkpoint(latest)
    if not goal_plan:
        raise ValueError("active plan cannot be restored")

    recovery_session_ids = _recovery_replan_session_ids_from_history(db, latest)
    repaired, changed_dates = rematerialize_non_executable_sessions(
        goal_plan,
        recovery_session_ids=recovery_session_ids,
    )
    if not changed_dates:
        return {
            "plan_id": None,
            "base_checkpoint_id": base_checkpoint_id,
            "changed_dates": [],
            "confirmation_required": False,
        }

    repaired = with_checkpoint_provenance(
        repaired,
        source="materialization_repair",
        parent_checkpoint_id=base_checkpoint_id,
    )
    saved = None
    if persist:
        saved = db.save_planning_checkpoint(build_planning_checkpoint(repaired))
    return {
        "plan_id": str(saved["id"]) if saved else None,
        "base_checkpoint_id": base_checkpoint_id,
        "changed_dates": changed_dates,
        "confirmation_required": not persist,
    }


def _infer_sport(parts: Any, template: Dict[str, Any] | None) -> str:
    sport = str((template or {}).get("sport") or "").strip()
    if sport and sport != "—":
        return sport
    parts = parts or {}
    if parts:
        return max(parts, key=lambda k: float(parts.get(k) or 0.0), default="bike")
    return "bike"


def _steps_payload(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "name": step.get("name"),
            "intensity": step.get("intensity"),
            "duration_seconds": step.get("duration_seconds"),
            "target": step.get("target"),
        }
        for step in list(session.get("materialized_steps") or [])
    ]


def _legs_payload(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "leg_index": leg.get("leg_index"),
            "leg_id": leg.get("leg_id"),
            "sport": leg.get("sport"),
            "template_name": leg.get("template_name"),
            "duration_minutes": leg.get("duration_minutes"),
            "target_tss": leg.get("target_tss"),
            "target_provenance": leg.get("target_provenance"),
            "steps": _steps_payload(dict(leg or {})),
        }
        for leg in list(session.get("legs") or [])
    ]


def _leaf_plan_payload(
    session: Dict[str, Any],
    *,
    phase: str,
) -> Dict[str, Any]:
    return {
        "session_id": session.get("session_id"),
        "replaces_session_id": session.get("replaces_session_id"),
        "sport": session.get("sport"),
        "sport_label": session.get("sport_label"),
        "role": str(session.get("session_role") or ""),
        "tss": float(session.get("total_tss") or 0.0),
        "duration_minutes": int(session.get("duration_minutes") or 0),
        "name": str(
            session.get("export_name")
            or session.get("template_name")
            or session.get("session_focus")
            or "Сессия"
        ),
        "phase": phase,
        "kind": str(session.get("kind") or "single"),
        "catalog_version": session.get("catalog_version"),
        "template_key": session.get("template_key"),
        "template_version": session.get("template_version"),
        "template_name": session.get("template_name"),
        "stimulus": session.get("stimulus"),
        "fatigue_cost": list(session.get("fatigue_cost") or []),
        "expected_recovery_hours": session.get("expected_recovery_hours"),
        "materialization_status": session.get("materialization_status"),
        "target_provenance": session.get("target_provenance"),
        "selection_evidence": session.get("selection_evidence"),
        "executable": not planned_session_requires_repair(session),
        "steps": _steps_payload(session),
        "legs": _legs_payload(session),
    }


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
        phase = str((tpl or {}).get("phase") or "")
        leaf_sessions = [
            dict(session or {})
            for session in list((tpl or {}).get("sessions") or [])
        ]
        if not leaf_sessions:
            leaf_sessions = [dict(tpl or {})]
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
                "phase": phase,
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
                "executable": not any(
                    planned_session_requires_repair(session)
                    for session in leaf_sessions
                ),
                "steps": _steps_payload(dict(tpl or {})),
                "legs": _legs_payload(dict(tpl or {})),
                "sessions": [
                    _leaf_plan_payload(session, phase=phase)
                    for session in leaf_sessions
                ],
            }
        )
    return out


_WEEK_BY_WEEK_MAX_WEEKS = 16
# The fact window must cover every displayed past week; otherwise a bounded
# reader would turn valid older evidence into fabricated missed sessions.
_WEEK_BY_WEEK_RECONCILIATION_WEEKS = _WEEK_BY_WEEK_MAX_WEEKS


def _week_by_week_number(value: Any) -> float:
    try:
        return round(float(value or 0.0), 1)
    except (TypeError, ValueError):
        return 0.0


def _week_by_week_status(
    match: Dict[str, Any] | None,
    *,
    planned_date: date,
    today: date,
) -> str:
    """Translate existing matching evidence into a reader state, without matching."""
    if planned_date > today:
        return "planned"
    match_status = str((match or {}).get("match_status") or "unmatched")
    if match_status == "ambiguous":
        return "ambiguous"
    if match_status == "matched":
        adherence = str((match or {}).get("adherence") or "unknown")
        return adherence if adherence in {"exact", "substituted", "major_deviation", "unknown"} else "unknown"
    # A calendar day is not over until its local date has passed (#268).
    return "in_progress" if planned_date == today else "missed"


def _week_by_week_window(
    rows: List[tuple[Dict[str, Any], date]],
    *,
    today: date,
) -> List[tuple[Dict[str, Any], date]]:
    """Keep the current week and a bounded surrounding plan window."""
    current_index = next(
        (index for index, (_row, start) in enumerate(rows) if start <= today <= start + timedelta(days=6)),
        None,
    )
    if current_index is None:
        current_index = next((index for index, (_row, start) in enumerate(rows) if start > today), len(rows) - 1)
    start_index = max(0, current_index - 4)
    end_index = min(len(rows), start_index + _WEEK_BY_WEEK_MAX_WEEKS)
    start_index = max(0, end_index - _WEEK_BY_WEEK_MAX_WEEKS)
    return rows[start_index:end_index]


def week_by_week_plan(db: Database) -> Dict[str, Any]:
    """Build one bounded plan/fact reader DTO from saved canonical projections."""
    goal_plan = get_active_plan(db)
    if not goal_plan:
        return {"has_plan": False, "state": "no_plan", "weeks": [], "chart": []}
    if not list(goal_plan.get("daily_plan") or []):
        return {
            "has_plan": True,
            "state": "data_gap",
            "reason": "В checkpoint нет дневного плана для сопоставления недель и сессий.",
            "weeks": [],
            "chart": [],
        }

    today = datetime.now().date()
    weekly_rows: List[tuple[Dict[str, Any], date]] = []
    for raw_week in list(goal_plan.get("weekly_summary") or []):
        if not isinstance(raw_week, dict):
            continue
        week_start = _overview_date(raw_week.get("week_start"))
        if week_start is not None:
            weekly_rows.append((dict(raw_week), week_start))
    weekly_rows.sort(key=lambda item: item[1])
    if not weekly_rows:
        return {
            "has_plan": True,
            "state": "data_gap",
            "reason": "В checkpoint нет дат недель активного плана.",
            "weeks": [],
            "chart": [],
        }
    selected_weeks = _week_by_week_window(weekly_rows, today=today)
    ordinal_by_week_start = {
        week_start.isoformat(): index + 1
        for index, (_week, week_start) in enumerate(weekly_rows)
    }

    # These two sources already own leaf materialization/exportability and
    # match semantics.  The reader joins their immutable output once here.
    exported_days = {int(item["index"]): item for item in plan_days(goal_plan)}
    reconciliation = reconciliation_at(
        db,
        weeks=_WEEK_BY_WEEK_RECONCILIATION_WEEKS,
        as_of=today,
        include_provider=False,
    )
    matches = {
        str(row.get("session_id")): dict(row)
        for row in list(reconciliation.get("rows") or [])
        if isinstance(row, dict) and row.get("session_id")
    }
    unplanned_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for raw_activity in list(reconciliation.get("unplanned_activities") or []):
        if not isinstance(raw_activity, dict):
            continue
        activity_date = _overview_date(raw_activity.get("date"))
        if activity_date is not None:
            unplanned_by_date.setdefault(activity_date.isoformat(), []).append(dict(raw_activity))

    daily_rows: Dict[str, tuple[int, Any]] = {}
    for index, item in enumerate(list(goal_plan.get("daily_plan") or [])):
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            continue
        planned_date = _overview_date(item[0])
        if planned_date is not None:
            daily_rows[planned_date.isoformat()] = (index, item)

    events_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for event in _overview_event_rows(goal_plan):
        events_by_date.setdefault(event["date"], []).append(event)

    weeks: List[Dict[str, Any]] = []
    chart_rows: List[Dict[str, Any]] = []
    for week, week_start in selected_weeks:
        week_end = week_start + timedelta(days=6)
        week_state = "past" if week_end < today else "future" if week_start > today else "current"
        days: List[Dict[str, Any]] = []
        for offset in range(7):
            day_date = week_start + timedelta(days=offset)
            iso_date = day_date.isoformat()
            entry = daily_rows.get(iso_date)
            parent_day = exported_days.get(entry[0]) if entry else None
            target_tss = _week_by_week_number(parent_day.get("tss") if parent_day else (entry[1][1] if entry else 0))
            unplanned = unplanned_by_date.get(iso_date, [])
            unplanned_tss = round(sum(_week_by_week_number(item.get("tss")) for item in unplanned), 1)
            sessions: List[Dict[str, Any]] = []
            actual_tss = 0.0
            if parent_day:
                for raw_session in list(parent_day.get("sessions") or []):
                    session = dict(raw_session)
                    match = matches.get(str(session.get("session_id") or ""))
                    session_actual = _week_by_week_number((match or {}).get("actual_total_tss"))
                    if match and str(match.get("match_status") or "") == "matched":
                        actual_tss += session_actual
                    sessions.append(
                        {
                            **session,
                            "adherence_status": _week_by_week_status(match, planned_date=day_date, today=today),
                            "actual_tss": session_actual if match and str(match.get("match_status")) == "matched" else None,
                            "actual_duration_minutes": _week_by_week_number((match or {}).get("actual_duration_minutes")) if match and str(match.get("match_status")) == "matched" else None,
                            "actual_activity_ids": list((match or {}).get("actual_activity_ids") or []),
                        }
                    )
            day_state = "past" if day_date < today else "future" if day_date > today else "current"
            plan_state = "planned" if target_tss > 0 else "unplanned" if unplanned_tss > 0 else "rest"
            days.append(
                {
                    "index": entry[0] if entry else None,
                    "date": iso_date,
                    "state": day_state,
                    "plan_state": plan_state,
                    "target_tss": target_tss,
                    "actual_tss": round(actual_tss, 1) if day_date <= today else None,
                    "unplanned_tss": unplanned_tss,
                    "unplanned_activities": unplanned,
                    "sessions": sessions,
                    "events": events_by_date.get(iso_date, []),
                }
            )

        target_tss = _week_by_week_number(week.get("weekly_tss"))
        actual_tss = round(sum(float(day["actual_tss"] or 0.0) for day in days), 1) if week_state != "future" else None
        unplanned_tss = round(sum(float(day["unplanned_tss"] or 0.0) for day in days), 1)
        statuses = [
            str(session["adherence_status"])
            for day in days
            for session in list(day["sessions"])
        ]
        completion_percent = (
            round((float(actual_tss or 0.0) / target_tss) * 100, 1)
            if week_state != "future" and target_tss > 0
            else None
        )
        week_events = [event for day in days for event in list(day["events"])]
        week_out = {
            "number": ordinal_by_week_start[week_start.isoformat()],
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "state": week_state,
            "is_current": week_state == "current",
            "phase": str(week.get("phase") or "Не указана"),
            "target_tss": target_tss,
            "actual_tss": actual_tss,
            "unplanned_tss": unplanned_tss,
            "completion_percent": completion_percent,
            "remaining_tss": round(max(0.0, target_tss - float(actual_tss or 0.0)), 1) if week_state == "current" else None,
            "adherence": {
                "exact": statuses.count("exact"),
                "substituted": statuses.count("substituted"),
                "major_deviation": statuses.count("major_deviation"),
                "ambiguous": statuses.count("ambiguous"),
                "missed": statuses.count("missed"),
                "in_progress": statuses.count("in_progress"),
            },
            "focus": [
                {
                    "sport": session.get("sport_label") or session.get("sport") or "—",
                    "role": session.get("role") or "",
                    "tss": session.get("tss") or 0,
                    "name": session.get("name") or "Сессия",
                }
                for day in days
                for session in list(day["sessions"])
                if str(session.get("role") or "") in {"quality", "long", "race"}
            ][:3],
            "events": week_events,
            "days": days,
        }
        weeks.append(week_out)
        chart_rows.append(
            {
                "number": week_out["number"],
                "week_start": week_out["week_start"],
                "phase": week_out["phase"],
                "state": week_state,
                "is_current": week_state == "current",
                "target_tss": target_tss,
                "actual_tss": actual_tss,
                "events": week_events,
            }
        )

    chart_maximum = max(
        (
            max(float(row["target_tss"] or 0.0), float(row["actual_tss"] or 0.0))
            for row in chart_rows
        ),
        default=0.0,
    )
    for row in chart_rows:
        row["target_percent"] = round((float(row["target_tss"]) / chart_maximum) * 100, 1) if chart_maximum else 0.0
        row["actual_percent"] = round((float(row["actual_tss"] or 0.0) / chart_maximum) * 100, 1) if row["actual_tss"] is not None and chart_maximum else None
    return {
        "has_plan": True,
        "state": "available",
        "as_of": today.isoformat(),
        "window": {"returned_weeks": len(weeks), "total_weeks": len(weekly_rows), "max_weeks": _WEEK_BY_WEEK_MAX_WEEKS},
        "chart": {"metric": "tss", "maximum_tss": chart_maximum, "weeks": chart_rows},
        "weeks": weeks,
        "data_quality": dict(reconciliation.get("data_quality") or {}),
    }


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
    session_id: str | None = None,
) -> Dict[str, str]:
    """Return {filename, mimetype, content} for a single planned session."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    templates = list(goal_plan.get("session_templates", []) or [])
    if index < 0 or index >= len(daily_plan):
        raise ValueError("day index out of range")

    dt, total, parts = daily_plan[index]
    tpl = templates[index] if index < len(templates) else {}
    sessions = [
        dict(session or {})
        for session in list((tpl or {}).get("sessions") or [])
    ]
    selected = dict(tpl or {})
    selected_position = 0
    if sessions:
        if session_id:
            selected_position = next(
                (
                    position
                    for position, session in enumerate(sessions)
                    if str(session.get("session_id") or "") == str(session_id)
                ),
                -1,
            )
            if selected_position < 0:
                raise ValueError(f"day has no session_id={session_id}")
            selected = sessions[selected_position]
        else:
            selected = sessions[0]
    elif session_id and str(selected.get("session_id") or "") != str(session_id):
        raise ValueError(f"day has no session_id={session_id}")

    kind = str(selected.get("kind") or "single")
    suffix = ""
    if kind == "composite":
        if leg not in {1, 2}:
            raise ValueError("composite session requires leg=1 or leg=2")
        require_executable_planned_session(selected)
        resolved_leg = next(
            (
                item
                for item in list(selected.get("legs") or [])
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
        sport = str(selected.get("sport") or "").strip() or _infer_sport(parts, tpl)
        steps = list(selected.get("materialized_steps") or [])
        if not steps:
            require_executable_planned_session(selected)
            steps = build_steps_for_sport(
                float(
                    selected.get("total_tss")
                    if selected.get("total_tss") is not None
                    else total or 0
                ),
                sport,
                session_role=str(selected.get("session_role", "easy")),
                phase=selected.get("phase") or (tpl or {}).get("phase"),
            )
        if session_id and len(sessions) > 1:
            suffix = f"_session{selected_position + 1}_{sport}"
    name = str(
        selected.get("export_name")
        or selected.get("template_name")
        or (tpl or {}).get("export_name")
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
    template, session = find_planned_session(goal_plan.get("session_templates", []) or [], session_id)
    if template is None or session is None:
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
            "sport": session.get("sport"),
            "role": session.get("session_role"),
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

    refresh_recovery_episodes_best_effort(db, as_of=date.today(), target_session_ids=[session_id])
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
    forecast = _forecast(
        banister,
        metrics,
        new_goal_plan.get("daily_plan", []),
        start_week,
        race_forecast_loads=new_goal_plan.get("race_forecast_loads"),
    )
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
    changed_indices: list[int] = []
    daily_plan = list(goal_plan.get("daily_plan") or [])
    templates = list(goal_plan.get("session_templates") or [])
    for row in draft_rows:
        try:
            index = int(row.get("index", -1))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(daily_plan):
            continue
        current_total = round(float(daily_plan[index][1] or 0.0), 1)
        template = dict(templates[index] or {}) if index < len(templates) else {}
        current_role = str(
            template.get("session_role")
            or ("off" if current_total <= 0 else "easy")
        ).strip().lower()
        current_sport = str(template.get("sport") or "off").strip().lower()
        target_total = round(float(row.get("total_tss") or 0.0), 1)
        target_role = str(row.get("session_role") or "easy").strip().lower()
        target_sport = str(row.get("sport") or "off").strip().lower()
        if (
            current_total != target_total
            or current_role != target_role
            or current_sport != target_sport
        ):
            changed_indices.append(index)
    assert_recovery_replan_safety(
        goal_plan,
        updated,
        target_indices=sorted(set(changed_indices)),
        expected_guard=proposal_params.get("safety_guard"),
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


def _recovery_transfer_session_label(session: Dict[str, Any]) -> str:
    """Human-readable label for a transferred session (Issue #223).

    Athlete-facing summaries must not read raw content-derived `ats_...`
    session ids (`models/session_identity.py`). Prefers the session's own
    `export_name`; falls back to its role + sport label when unset, and
    always carries TSS so the athlete sees what actually moved.
    """
    role_label = SESSION_ROLE_LABELS_RU.get(str(session.get("session_role") or ""), "")
    sport_label = str(session.get("sport_label") or "").strip()
    name = str(session.get("export_name") or "").strip() or " • ".join(
        part for part in (role_label, sport_label) if part
    ) or "Сессия"
    try:
        tss = int(round(float(session.get("total_tss") or 0.0)))
    except (TypeError, ValueError):
        tss = 0
    return f"{name} ({tss} TSS)"


def apply_recovery_replan_transfer(
    db: Database,
    *,
    base_checkpoint_id: int,
    session_id: str,
    target_date: str,
    persist: bool = True,
) -> Dict[str, Any]:
    """Apply a confirmed `transfer_1_3d` variant against its exact base checkpoint.

    Routes ONLY through the shared atomic primitive
    `models/session_transfer.py::apply_session_transfer` — never the
    near-term editor — reusing the preview's own `session_id`/`target_date`
    so the ranker's promise and the applied result cannot diverge (Issue
    #209 M4).
    """
    latest = db.get_latest_planning_checkpoint()
    latest_id = int(latest.get("id")) if isinstance(latest, dict) and latest.get("id") else None
    if latest_id != base_checkpoint_id:
        raise StalePlanningCheckpointError(
            f"active checkpoint #{latest_id} no longer matches proposal base #{base_checkpoint_id}"
        )

    goal_plan = restore_goal_plan_from_checkpoint(latest)
    if not goal_plan or not goal_plan.get("daily_plan"):
        raise ValueError("active plan cannot be restored")

    wanted = str(session_id or "").strip()
    source_date = None
    for template in list(goal_plan.get("session_templates") or []):
        if not isinstance(template, dict):
            continue
        for session in list(template.get("sessions") or []):
            if isinstance(session, dict) and str(session.get("session_id") or "") == wanted:
                source_date = str(template.get("date") or "")[:10]
                break
        if source_date is not None:
            break

    applied = apply_session_transfer(goal_plan, session_id=session_id, target_date=target_date)
    moved_plan = with_checkpoint_provenance(
        applied["goal_plan"],
        source="recovery_replan_transfer",
        parent_checkpoint_id=base_checkpoint_id,
    )

    new_session_label = ""
    target_date_iso = str(target_date)[:10]
    for template in list(applied["goal_plan"].get("session_templates") or []):
        if not isinstance(template, dict) or str(template.get("date") or "")[:10] != target_date_iso:
            continue
        for session in list(template.get("sessions") or []):
            if isinstance(session, dict) and str(session.get("session_id") or "") == applied["new_session_id"]:
                new_session_label = _recovery_transfer_session_label(session)
                break
        if new_session_label:
            break

    saved = None
    plan_id = None
    if persist:
        saved = db.save_planning_checkpoint(build_planning_checkpoint(moved_plan))
        plan_id = str((saved or {}).get("id") or "")

    affected_dates = sorted({d for d in (source_date, target_date_iso) if d})
    return {
        "plan_id": plan_id,
        "applied_checkpoint_id": int(plan_id) if plan_id else None,
        "rollback_checkpoint_id": base_checkpoint_id,
        "checkpoint_source": "recovery_replan_transfer",
        "old_session_id": applied["old_session_id"],
        "new_session_id": applied["new_session_id"],
        "new_session_label": new_session_label,
        "affected_dates": affected_dates,
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

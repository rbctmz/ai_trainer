"""Headless plan building over the existing training_planner pipeline.

Replicates the exact sequence the Streamlit "Собрать план" button runs
(`create_weekly_tss_plan` → `apply_planning_constraints` →
`expand_weekly_to_daily_triathlon` → `build_daily_session_templates`), then
forecasts CTL/ATL/TSB with `BanisterModel.simulate_variable_load`. No training
math is reimplemented here — only orchestration + JSON shaping.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from api.readiness_snapshot import build_readiness_snapshot
from data.database import Database
from models.banister import BanisterModel, tsb_zone
from models.fit_export import build_steps_for_sport, generate_fit_csv
from models.planning_checkpoints import (
    build_planning_checkpoint,
    restore_goal_plan_from_checkpoint,
    summarize_planning_checkpoint,
    with_checkpoint_provenance,
)
from models.planning_execution import (
    build_execution_plan_adjustment,
    build_execution_reconciliation_rows,
    rebuild_goal_plan_with_adjustment,
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
    apply_planning_constraints,
    build_daily_session_templates,
    compute_phase_schedule,
    create_ics_from_daily,
    create_weekly_tss_plan,
    expand_weekly_to_daily_triathlon,
    flatten_daily_total,
    weeks_until,
)

PLANNING_DEMAND_SETTING_KEY = "planning_demand_level"

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


def current_status(db: Database) -> Dict[str, Any]:
    signals, _df = _current_signals(db)
    metrics = _metrics_from_signals(signals)
    checkpoint = summarize_planning_checkpoint(db.get_latest_planning_checkpoint())
    return {
        "metrics": {
            "ctl": round(float(metrics.get("ctl") or 0.0), 1),
            "atl": round(float(metrics.get("atl") or 0.0), 1),
            "tsb": round(float(metrics.get("tsb") or 0.0), 1),
            "form": metrics.get("form", "Недостаточно данных"),
        },
        "readiness_snapshot": build_readiness_snapshot(db),
        "signals": signals,
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
    event_date: str,
    available_hours: float,
    available_days: Optional[List[str]] = None,
    demand: Optional[str] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    metrics, banister, activities_df = _current_metrics(db)
    gt = _internal_goal_type(goal_type)
    dist = _internal_distance(distance)
    day_indices = _day_indices(available_days)

    start_week = _start_week()
    goal_dt = datetime.strptime(event_date[:10], "%Y-%m-%d").date()
    weeks_to_race = max(1, weeks_until(goal_dt, from_date=start_week))

    start_weekly_tss_guess = int(float(metrics.get("ctl", 50) or 50) * 7)
    demand_level = normalize_demand_level(demand or _persisted_demand_level(db))
    if demand is not None:
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
        weeks_total=weeks_to_race,
        target_weekly_tss=target_weekly_tss,
        deload_every=4,
        taper_weeks=2,
        max_ramp=0.10,
    )
    phases = compute_phase_schedule(weeks_to_race)

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

    session_templates = build_daily_session_templates(
        daily_plan, weekly_summary, goal_type=gt, distance=dist
    )

    goal_plan = with_checkpoint_provenance(
        {
            "goal_type": gt,
            "distance": dist,
            "weeks_to_race": weeks_to_race,
            "start_week": start_week,
            "weekly_tss_plan": weekly_tss_plan,
            "base_weekly_tss_plan": base_weekly,
            "phases": phases,
            "daily_plan": daily_plan,
            "session_templates": session_templates,
            "weekly_summary": weekly_summary,
            "constraint_summary": constraint_summary,
            "demand_level": demand_level,
            "demand_multiplier": float(target_breakdown["demand"]["multiplier"]),
            "weekly_target_breakdown": target_breakdown,
            "planner_mix": mix_overrides,
            "planner_weights": None,
            "plan_revision": datetime.now().isoformat(),
            "near_term_edit_version": 0,
            "near_term_edit_rollback_target_checkpoint_id": None,
        },
        source="initial_plan",
    )

    plan_id: Optional[str] = None
    if persist:
        saved = db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))
        plan_id = str((saved or {}).get("id") or (saved or {}).get("checkpoint_id") or "")

    forecast = _forecast(banister, metrics, daily_plan, start_week)
    weeks = _weeks_payload(weekly_summary, phases)
    total_tss = int(sum(int(w or 0) for w in weekly_tss_plan))
    peak_tss = int(max(weekly_tss_plan) if weekly_tss_plan else 0)

    return {
        "plan_id": plan_id,
        "goal": {
            "goal_type": gt,
            "distance": dist,
            "event_date": goal_dt.isoformat(),
            "weeks_to_race": weeks_to_race,
        },
        "weekly_target": {
            **public_weekly_target_payload(target_breakdown),
        },
        "totals": {"peak_tss": peak_tss, "total_tss": total_tss},
        "weeks": weeks,
        "forecast": forecast,
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
    return restore_goal_plan_from_checkpoint(db.get_latest_planning_checkpoint())


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
                "date": (dt.date() if hasattr(dt, "date") else dt).isoformat(),
                "sport": _infer_sport(parts, tpl),
                "sport_label": str((tpl or {}).get("sport_label") or _infer_sport(parts, tpl)),
                "tss": total_tss,
                "name": str((tpl or {}).get("export_name") or (tpl or {}).get("session_focus") or "Сессия"),
                "phase": str((tpl or {}).get("phase") or ""),
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


def export_workout(goal_plan: Dict[str, Any], index: int, fmt: str) -> Dict[str, str]:
    """Return {filename, mimetype, content} for a single planned session."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    templates = list(goal_plan.get("session_templates", []) or [])
    if index < 0 or index >= len(daily_plan):
        raise ValueError("day index out of range")

    dt, total, parts = daily_plan[index]
    tpl = templates[index] if index < len(templates) else {}
    sport = _infer_sport(parts, tpl)
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
            "filename": f"workout_{stamp}.csv",
            "mimetype": "text/csv",
            "content": generate_fit_csv(name, sport, steps, created=dt),
        }
    if fmt == "tcx_activity":
        content = generate_tcx_activity(
            name, sport, steps, start_time=datetime.combine(dt.date(), datetime.min.time())
        )
        return {
            "filename": f"activity_{stamp}.tcx",
            "mimetype": "application/vnd.garmin.tcx+xml",
            "content": content,
        }
    # default: structured TCX workout
    return {
        "filename": f"workout_{stamp}.tcx",
        "mimetype": "application/vnd.garmin.tcx+xml",
        "content": generate_tcx_workout(name, sport, steps, created=dt),
    }


# ---------------------------------------------------------------------------
# Adjust mode (execution feedback → rebuilt plan)
# ---------------------------------------------------------------------------
def reconciliation(db: Database, weeks: int = 1) -> Dict[str, Any]:
    goal_plan = get_active_plan(db)
    if not goal_plan or not goal_plan.get("daily_plan"):
        return {"has_plan": False, "rows": []}
    rows = build_execution_reconciliation_rows(
        goal_plan, weeks=weeks, recent_activities=db.get_activities(30)
    )
    return {"has_plan": True, "weeks": weeks, "rows": rows}


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
    new_goal_plan = with_checkpoint_provenance(
        rebuild_goal_plan_with_adjustment(goal_plan, adjustment),
        source="execution_adjustment",
    )

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
        "weeks": weeks_payload,
        "forecast": forecast,
    }


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

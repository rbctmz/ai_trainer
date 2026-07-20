"""Dashboard endpoints.

Uses headless dashboard builders shared with the Streamlit fallback so both
surfaces show the same numbers without coupling FastAPI to legacy UI modules.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict

import pandas as pd
from fastapi import APIRouter, Depends

from api.deps import get_database, get_headless_state
from api.operational_state import build_operational_state, latest_iso_from_frame
from api.readiness_snapshot import build_readiness_snapshot
from data.database import Database
from models.banister import tsb_zone
from state import StateManager
from models.dashboard_summary import (
    build_activity_day_tss,
    build_dashboard_summary,
    build_plan_day_lookup,
    calculate_current_status,
    get_dashboard_goal_plan,
    get_latest_training_status,
    project_readiness_snapshot,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(
    demo: bool = False,
    db: Database = Depends(get_database),
    state: StateManager = Depends(get_headless_state),
) -> Dict[str, Any]:
    """Command-center summary: today's state, workout, week load, next action."""
    readiness_snapshot = build_readiness_snapshot(db)
    activities_df = db.get_activities(30)
    if activities_df is None or activities_df.empty:
        return {
            "has_data": False,
            "summary": None,
            "readiness_snapshot": readiness_snapshot,
            "operational_state": build_operational_state(db, demo=demo, has_data=False),
        }

    hrv_df = db.get_hrv_data(90)
    sleep_df = db.get_sleep_data(7)

    latest_training_status = get_latest_training_status(db)
    current_status = calculate_current_status(
        activities_df,
        hrv_df,
        sleep_df,
        training_status=latest_training_status,
    )
    current_status = project_readiness_snapshot(current_status, readiness_snapshot)
    summary = build_dashboard_summary(
        state,
        current_status,
        latest_training_status,
        activities_df,
    )
    return {
        "has_data": True,
        "summary": summary,
        "signals": current_status.get("signals"),
        "readiness_snapshot": readiness_snapshot,
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=True,
            latest_data_at=latest_iso_from_frame(activities_df),
        ),
    }


# ---------------------------------------------------------------------------
# Widgets endpoint — Training Score, Daily Outlook, Race Projection
# ---------------------------------------------------------------------------

def _ctl_series(activities_df: pd.DataFrame, days: int = 90) -> dict[date, float]:
    """Return {date: ctl} over the last `days` days using Banister 42-day decay."""
    today = datetime.now().date()
    start = today - timedelta(days=days)
    tss_by_date: dict[date, float] = {}
    if activities_df is not None and not activities_df.empty:
        df = activities_df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        for _, row in df.iterrows():
            d = row["date"]
            tss = float(row.get("tss") or 0)
            tss_by_date[d] = tss_by_date.get(d, 0.0) + tss

    series: dict[date, float] = {}
    ctl = 0.0
    current = start
    while current <= today:
        tss = tss_by_date.get(current, 0.0)
        ctl = ctl + (tss - ctl) / 42
        series[current] = round(ctl, 2)
        current += timedelta(days=1)
    return series


def _calculate_training_score(
    ctl: float,
    tsb: float,
    actual_week_tss: float,
    planned_week_tss: float,
    ramp_rate: float,
) -> dict[str, Any]:
    # Fitness (0–100): based on CTL
    fitness = min(100, int(ctl * 1.15))
    fitness_label = (
        "Низкая" if ctl < 25
        else "Умеренная" if ctl < 50
        else "Высокая" if ctl < 80
        else "Элитная"
    )

    # Progression (0–100): ramp rate
    if ramp_rate >= 3:
        prog = min(90, 60 + int(ramp_rate * 4))
        prog_label = "Растёт"
    elif ramp_rate >= 0:
        prog = 45
        prog_label = "Стабильно"
    elif ramp_rate >= -2:
        prog = 30
        prog_label = "Снижается"
    else:
        prog = max(0, 20 + int(ramp_rate * 3))
        prog_label = "Падает"

    # Consistency (0–100): adherence
    if planned_week_tss > 0:
        adherence = min(1.0, actual_week_tss / planned_week_tss)
        cons = int(adherence * 100)
    else:
        adherence = 0.5
        cons = 50
    cons_label = f"{int(adherence * 100)}% выполнения"

    # Load Mgmt (0–100): smooth score curve stays independent of the
    # canonical 4-zone boundaries (it's a continuous contribution to the
    # composite Training Score, not a zone description) — only the label
    # is aligned to tsb_zone() so it stops disagreeing with the rest of
    # this page about what the same TSB value means.
    if -10 <= tsb <= 20:
        load = 85
    elif tsb > 20:
        load = 70
    elif tsb > -25:
        load = 55
    else:
        load = max(15, 40 + int(tsb * 1.2))
    load_label = tsb_zone(tsb)["label"]

    total = int(fitness * 0.30 + prog * 0.25 + cons * 0.25 + load * 0.20)
    total_label = (
        "Отлично" if total >= 80
        else "Хорошо" if total >= 60
        else "Нормально" if total >= 40
        else "Нужна работа"
    )

    return {
        "total": total,
        "label": total_label,
        "fitness":     {"score": fitness, "label": fitness_label, "detail": f"CTL {int(ctl)}"},
        "progression": {"score": prog,    "label": prog_label,    "detail": f"{ramp_rate:+.1f} CTL/нед"},
        "consistency": {"score": cons,    "label": cons_label,    "detail": f"{int(adherence * 100)}%"},
        "load_mgmt":   {"score": load,    "label": load_label,    "detail": f"TSB {tsb:+.1f}"},
    }


def _generate_daily_outlook(
    goal_plan: dict[str, Any] | None,
    ctl: float,
    tsb: float,
    hrv: float | None,
    sleep_hours: float | None,
    readiness: float,
) -> dict[str, Any]:
    from models.training_planner import current_periodization_phase

    parts: list[str] = []
    zone = tsb_zone(tsb)
    resolved_phase = current_periodization_phase(goal_plan)
    if resolved_phase:
        parts.append(f"Фаза «{resolved_phase['phase']}», {zone['clause']} (TSB {tsb:+.1f}).")
    else:
        clause = zone["clause"][0].upper() + zone["clause"][1:]
        parts.append(f"{clause} (TSB {tsb:+.1f}).")

    flags: list[str] = []
    if sleep_hours is not None and sleep_hours < 6.0:
        flags.append(f"короткий сон ({sleep_hours:.1f} ч)")
    if hrv is not None and hrv < 38:
        flags.append(f"низкий HRV ({int(hrv)})")
    if readiness > 0 and readiness < 40:
        flags.append(f"низкая готовность ({int(readiness)})")

    if flags:
        parts.append(f"Красные флаги: {', '.join(flags)}. Снизьте интенсивность.")
        flags_tone = "warning"
    else:
        parts.append("Сигналы восстановления в норме — ограничений нет.")
        flags_tone = "neutral"

    # Card border reflects the worse of (TSB zone, red-flag severity) so it
    # never looks calmer than the text it's framing.
    _TONE_SEVERITY = {"danger": 3, "warning": 2, "neutral": 1, "success": 0}
    tone = max((zone["tone"], flags_tone), key=lambda t: _TONE_SEVERITY[t])

    if ctl < 20:
        parts.append("Идёт набор базовой формы — ключевое сейчас регулярность.")
    elif ctl > 55:
        parts.append("Высокая форма — следите за балансом нагрузки и восстановления.")

    return {"text": " ".join(parts), "tone": tone}


def _calculate_race_projection(
    goal_plan: dict[str, Any],
    current_ctl: float,
    current_tsb: float,
    activities_df: pd.DataFrame | None,
) -> dict[str, Any] | None:
    event_date_str = str(goal_plan.get("event_date") or "").strip()
    if not event_date_str:
        return None
    try:
        event_date = date.fromisoformat(event_date_str[:10])
        today = datetime.now().date()
        days_to_race = (event_date - today).days
        if days_to_race < 0 or days_to_race > 400:
            return None

        plan_lookup = build_plan_day_lookup(goal_plan)
        ctl = current_ctl
        atl = max(0.0, current_ctl - current_tsb)

        for offset in range(1, days_to_race + 1):
            d = today + timedelta(days=offset)
            planned_tss = float(plan_lookup.get(d, {}).get("total_tss") or 0)
            ctl = ctl + (planned_tss - ctl) / 42
            atl = atl + (planned_tss - atl) / 7

        projected_ctl = round(ctl, 1)
        projected_tsb = round(ctl - atl, 1)

        # Target from plan or fallback
        target_ctl = float(goal_plan.get("target_ctl") or 0)
        if target_ctl <= 0:
            # Estimate: peak CTL from weekly plan
            peak_tss_week = max(
                (float(goal_plan.get("weekly_tss_target") or 0),
                 current_ctl * 1.2),
            )
            target_ctl = peak_tss_week / 7 * (1 / (1 - 1 / 42))  # steady-state CTL estimate
            target_ctl = max(target_ctl, current_ctl)

        behind = target_ctl > 0 and projected_ctl < target_ctl * 0.92
        status = "behind" if behind else "on_track"
        label = "Отстаёте от плана" if behind else "По плану"

        fresh_for_race = -15 <= projected_tsb <= 25

        return {
            "event_date": event_date.isoformat(),
            "days_to_race": days_to_race,
            "projected_ctl": projected_ctl,
            "projected_tsb": projected_tsb,
            "fresh_for_race": fresh_for_race,
            "status": status,
            "label": label,
        }
    except Exception:
        return None


@router.get("/widgets")
def dashboard_widgets(
    db: Database = Depends(get_database),
    state: StateManager = Depends(get_headless_state),
) -> Dict[str, Any]:
    """Secondary dashboard widgets: Training Score, Daily Outlook, Race Projection."""
    readiness_snapshot = build_readiness_snapshot(db)
    # Keep 90 days for ramp-rate history and weekly lookup. The initial signal
    # assembly remains backward-compatible, then project_readiness_snapshot()
    # replaces today's readiness/CTL/ATL/TSB with the canonical 90-day fusion
    # used by Dashboard summary, Planning, and Coach (issue #152).
    activities_df = db.get_activities(90)
    activities_df_30 = db.get_activities(30)
    sleep_df = db.get_sleep_data(7)
    hrv_df = db.get_hrv_data(30)

    empty = activities_df is None or activities_df.empty
    empty_30 = activities_df_30 is None or activities_df_30.empty
    latest_training_status = get_latest_training_status(db)
    current_status = calculate_current_status(
        activities_df_30 if not empty_30 else pd.DataFrame(),
        hrv_df,
        sleep_df,
        training_status=latest_training_status,
    )
    current_status = project_readiness_snapshot(current_status, readiness_snapshot)
    signals = current_status.get("signals")

    # Fresh/empty account (no activity history in 90 days) → CTL/ATL/TSB are all
    # zero. Feeding those zeros into the score fabricates confident defaults that
    # flatly contradict has_data: TSB +0.0 → "Стабильная нагрузка" (load 85),
    # ramp 0 → "Стабильно" (prog 45), no plan → adherence 0.5 → "50% выполнения"
    # (cons 50), composite total 40 "Нормально", plus a Daily Outlook asserting
    # "восстановление в норме — ограничений нет". Withhold the derived widgets
    # instead — mirror /summary, which returns summary: None when has_data False.
    if empty:
        return {
            "has_data": False,
            "readiness_snapshot": readiness_snapshot,
            "training_score": None,
            "daily_outlook": None,
            "race_projection": None,
            "signals": signals,
        }

    goal_plan = get_dashboard_goal_plan(state)

    ctl = float(current_status.get("ctl") or 0)
    tsb = float(current_status.get("tsb") or 0)
    hrv = current_status.get("hrv") or latest_training_status.get("hrv")
    readiness = float(current_status.get("readiness") or 0)

    # Latest sleep
    sleep_hours: float | None = None
    if sleep_df is not None and not sleep_df.empty:
        latest_sleep = sleep_df.sort_values("date").iloc[-1]
        total_mins = latest_sleep.get("total_sleep_minutes")
        try:
            if total_mins and not pd.isna(total_mins):
                sleep_hours = round(float(total_mins) / 60, 1)
        except (TypeError, ValueError):
            pass

    # Ramp rate from CTL series (past the empty guard, activities_df is non-empty)
    ctl_series = _ctl_series(activities_df)
    today = datetime.now().date()
    ctl_4w = ctl_series.get(today - timedelta(days=28), ctl)
    ramp_rate = round((ctl - ctl_4w) / 4, 1)

    # Weekly consistency
    week_start = today - timedelta(days=today.weekday())
    week_days = [week_start + timedelta(days=i) for i in range(7)]
    plan_lookup = build_plan_day_lookup(goal_plan)
    activity_tss_by_day = build_activity_day_tss(activities_df)
    planned_week_tss = sum(float(plan_lookup.get(d, {}).get("total_tss") or 0) for d in week_days)
    actual_week_tss = sum(float(activity_tss_by_day.get(d, 0)) for d in week_days)

    return {
        "has_data": True,
        "readiness_snapshot": readiness_snapshot,
        "training_score": _calculate_training_score(
            ctl, tsb, actual_week_tss, planned_week_tss, ramp_rate
        ),
        "daily_outlook": _generate_daily_outlook(
            goal_plan, ctl, tsb, hrv, sleep_hours, readiness
        ),
        "race_projection": _calculate_race_projection(
            goal_plan, ctl, tsb, activities_df
        ),
        "signals": signals,
    }

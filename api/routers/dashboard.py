"""Dashboard endpoints.

Reuses the existing, tested command-center builder
``ui.pages.dashboard._build_dashboard_v2_summary`` so the web dashboard shows
exactly the same numbers as the Streamlit one. No metrics are recomputed here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict

import pandas as pd
from fastapi import APIRouter, Depends

from api.deps import get_database, get_headless_state
from data.database import Database
from state import StateManager
from ui.pages.dashboard import (
    _build_activity_day_tss,
    _build_dashboard_v2_summary,
    _build_plan_day_lookup,
    _calculate_current_status,
    _get_dashboard_goal_plan,
    _get_latest_training_status,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(
    db: Database = Depends(get_database),
    state: StateManager = Depends(get_headless_state),
) -> Dict[str, Any]:
    """Command-center summary: today's state, workout, week load, next action."""
    activities_df = db.get_activities(30)
    if activities_df is None or activities_df.empty:
        return {"has_data": False, "summary": None}

    hrv_df = db.get_hrv_data(90)
    sleep_df = db.get_sleep_data(7)

    current_status = _calculate_current_status(activities_df, hrv_df, sleep_df)
    latest_training_status = _get_latest_training_status(db)
    summary = _build_dashboard_v2_summary(
        state,
        current_status,
        latest_training_status,
        activities_df,
    )
    return {"has_data": True, "summary": summary}


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

    # Load Mgmt (0–100): TSB zone
    if -10 <= tsb <= 20:
        load = 85
        load_label = "Оптимальная зона"
    elif tsb > 20:
        load = 70
        load_label = "Очень свежий"
    elif tsb > -25:
        load = 55
        load_label = "Умеренная усталость"
    else:
        load = max(15, 40 + int(tsb * 1.2))
        load_label = "Высокая усталость"

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
    phase: str,
    ctl: float,
    tsb: float,
    hrv: float | None,
    sleep_hours: float | None,
    readiness: float,
) -> dict[str, Any]:
    parts: list[str] = []

    if tsb > 10:
        parts.append(f"Фаза «{phase}», хорошая свежесть (TSB {tsb:+.1f}) — можно работать на качество.")
    elif tsb > -10:
        parts.append(f"Фаза «{phase}», умеренная нагрузка (TSB {tsb:+.1f}) — придерживайтесь плана.")
    else:
        parts.append(f"Фаза «{phase}», накопленная усталость (TSB {tsb:+.1f}) — контролируйте интенсивность.")

    flags: list[str] = []
    if sleep_hours is not None and sleep_hours < 6.0:
        flags.append(f"короткий сон ({sleep_hours:.1f} ч)")
    if hrv is not None and hrv < 38:
        flags.append(f"низкий HRV ({int(hrv)})")
    if readiness > 0 and readiness < 40:
        flags.append(f"низкая готовность ({int(readiness)})")

    if flags:
        parts.append(f"Красные флаги: {', '.join(flags)}. Снизьте интенсивность.")
        tone = "warning"
    else:
        parts.append("Сигналы восстановления в норме — ограничений нет.")
        tone = "neutral"

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

        plan_lookup = _build_plan_day_lookup(goal_plan)
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
    activities_df = db.get_activities(90)
    sleep_df = db.get_sleep_data(7)
    hrv_df = db.get_hrv_data(30)

    empty = activities_df is None or activities_df.empty
    current_status = _calculate_current_status(
        activities_df if not empty else pd.DataFrame(), hrv_df, sleep_df
    )
    latest_training_status = _get_latest_training_status(db)
    goal_plan = _get_dashboard_goal_plan(state)

    ctl = float(current_status.get("ctl") or 0)
    tsb = float(current_status.get("tsb") or 0)
    hrv = current_status.get("hrv") or latest_training_status.get("hrv")
    readiness = float(
        latest_training_status.get("training_readiness")
        or current_status.get("readiness")
        or 0
    )

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

    # Ramp rate from CTL series
    ctl_series = _ctl_series(activities_df if not empty else None)
    today = datetime.now().date()
    ctl_4w = ctl_series.get(today - timedelta(days=28), ctl)
    ramp_rate = round((ctl - ctl_4w) / 4, 1)

    # Weekly consistency
    week_start = today - timedelta(days=today.weekday())
    week_days = [week_start + timedelta(days=i) for i in range(7)]
    plan_lookup = _build_plan_day_lookup(goal_plan)
    activity_tss_by_day = _build_activity_day_tss(
        activities_df if not empty else pd.DataFrame()
    )
    planned_week_tss = sum(float(plan_lookup.get(d, {}).get("total_tss") or 0) for d in week_days)
    actual_week_tss = sum(float(activity_tss_by_day.get(d, 0)) for d in week_days)

    # Phase from checkpoint
    checkpoint = getattr(state, "latest_planning_checkpoint", None)
    phase = "Base"
    if isinstance(checkpoint, dict):
        snapshot = checkpoint.get("goal_plan_snapshot") or {}
        raw_phase = snapshot.get("current_phase") or checkpoint.get("load_state_label") or ""
        if raw_phase:
            phase = str(raw_phase)

    return {
        "has_data": not empty,
        "training_score": _calculate_training_score(
            ctl, tsb, actual_week_tss, planned_week_tss, ramp_rate
        ),
        "daily_outlook": _generate_daily_outlook(
            phase, ctl, tsb, hrv, sleep_hours, readiness
        ),
        "race_projection": _calculate_race_projection(
            goal_plan, ctl, tsb, activities_df if not empty else None
        ),
    }

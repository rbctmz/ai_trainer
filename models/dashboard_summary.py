"""Headless builders shared by the Dashboard API and Streamlit fallback."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import logging
from typing import Any

import pandas as pd

from models.banister import tsb_zone
from models.coach_explainability import build_coach_explainability_summary
from models.planning_checkpoints import summarize_planning_checkpoint
from models.signals_engine import assemble_signals, current_status_from_signals
from utils.product_semantics import (
    format_date_label,
    normalize_sport_key,
    sport_label,
)


logger = logging.getLogger(__name__)

_TONE_SEVERITY = {"success": 0, "neutral": 1, "warning": 2, "danger": 3}


def _readiness_presentation(status: str) -> tuple[str, str]:
    return {
        "low": ("Низкая готовность", "danger"),
        "limited": ("Ограниченная готовность", "warning"),
        "ready": ("Контролируемая готовность", "neutral"),
        "strong": ("Готов к работе", "success"),
        "stale": ("Данные требуют обновления", "warning"),
    }.get(status, ("Недостаточно данных", "neutral"))


def project_readiness_snapshot(
    current_status: dict[str, Any],
    readiness_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return status with canonical readiness/load values, without mutation."""
    projected = deepcopy(current_status)
    if not isinstance(readiness_snapshot, dict):
        return projected

    score = readiness_snapshot.get("score")
    if score is None:
        return projected

    status = str(readiness_snapshot.get("status") or "unknown")
    state_label, tone = _readiness_presentation(status)
    projected.update(
        {
            "readiness": float(score),
            "readiness_source": "canonical_snapshot",
            "state_label": state_label,
            "tone": tone,
        }
    )

    load = readiness_snapshot.get("tsb") or {}
    for key in ("ctl", "atl", "tsb"):
        value = load.get(key)
        if value is not None:
            projected[key] = float(value)

    hrv_factor = next(
        (
            factor
            for factor in (readiness_snapshot.get("factors") or [])
            if factor.get("key") == "hrv" and factor.get("raw_value") is not None
        ),
        None,
    )
    if hrv_factor is not None:
        projected["hrv"] = float(hrv_factor["raw_value"])

    signals = projected.get("signals")
    if isinstance(signals, dict):
        readiness_signal = dict(signals.get("readiness") or {})
        readiness_signal.update(
            {
                "value": float(score),
                "label": state_label,
                "tone": tone,
                "severity": _TONE_SEVERITY[tone],
                "source": "canonical_snapshot",
                "drivers": list(readiness_snapshot.get("drivers") or []),
            }
        )
        signals["readiness"] = readiness_signal

        if projected.get("tsb") is not None:
            zone = tsb_zone(float(projected["tsb"]))
            load_signal = dict(signals.get("load") or {})
            load_signal.update(
                {
                    "ctl": projected.get("ctl"),
                    "atl": projected.get("atl"),
                    "tsb": projected.get("tsb"),
                    "label": zone["label"],
                    "tone": zone["tone"],
                    "clause": zone["clause"],
                    "severity": _TONE_SEVERITY[zone["tone"]],
                }
            )
            signals["load"] = load_signal

        state_signal = dict(signals.get("state") or {})
        state_signal.update(
            {"label": state_label, "tone": tone, "severity": _TONE_SEVERITY[tone]}
        )
        signals["state"] = state_signal
        projected["signals"] = signals

    return projected


def _coerce_dashboard_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            return None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _format_tss_value(value: Any) -> str:
    try:
        return f"{float(value or 0):.0f}"
    except (TypeError, ValueError):
        return "0"


def get_dashboard_goal_plan(state: Any) -> dict[str, Any]:
    goal_plan = getattr(state, "resolved_goal_plan_context", None)
    if not isinstance(goal_plan, dict) or not goal_plan:
        goal_plan = getattr(state, "goal_plan", None)
    if not isinstance(goal_plan, dict) or not goal_plan:
        # Headless API mode: state.goal_plan is never set; fall back to DB checkpoint.
        # latest_planning_checkpoint has lazy-loading via refresh_planning_checkpoint_cache().
        checkpoint = getattr(state, "latest_planning_checkpoint", None)
        if isinstance(checkpoint, dict):
            from models.planning_checkpoints import restore_goal_plan_from_checkpoint

            goal_plan = restore_goal_plan_from_checkpoint(checkpoint)
    return goal_plan if isinstance(goal_plan, dict) else {}


def build_plan_day_lookup(goal_plan: dict[str, Any]) -> dict[date, dict[str, Any]]:
    from models.training_planner import iter_leaf_sessions

    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    session_templates = list(goal_plan.get("session_templates", []) or [])
    lookup: dict[date, dict[str, Any]] = {}
    for idx, entry in enumerate(daily_plan):
        try:
            planned_dt, total_tss, parts = entry
        except (TypeError, ValueError):
            continue
        planned_date = _coerce_dashboard_date(planned_dt)
        if planned_date is None:
            continue
        template = (
            session_templates[idx]
            if idx < len(session_templates) and isinstance(session_templates[idx], dict)
            else {}
        )
        sport = str(template.get("sport") or "").strip()
        if not sport and isinstance(parts, dict):
            sport = max(parts, key=lambda key: float(parts.get(key) or 0.0), default="")
        lookup[planned_date] = {
            "date": planned_date,
            "index": idx,
            "total_tss": float(total_tss or 0.0),
            "parts": parts if isinstance(parts, dict) else {},
            "sport": sport or "—",
            "name": str(
                template.get("export_name")
                or template.get("name")
                or "Плановая тренировка"
            ),
            "duration_minutes": int(template.get("duration_minutes") or 0),
            "session_role": str(
                template.get("session_role_label") or template.get("session_role") or ""
            ),
            # Issue #205 milestone 2.6: ordered executable leaf sessions of the
            # day (single sessions and brick legs separately); rest/race -> [].
            "sessions": iter_leaf_sessions(template),
        }
    return lookup


def build_activity_day_tss(activities_df: pd.DataFrame) -> dict[date, float]:
    if activities_df.empty or "date" not in activities_df.columns:
        return {}
    activity_days: dict[date, float] = {}
    for _, row in activities_df.iterrows():
        activity_date = _coerce_dashboard_date(row.get("date"))
        if activity_date is None:
            continue
        try:
            tss_value = float(row.get("tss") or 0.0)
        except (TypeError, ValueError):
            tss_value = 0.0
        activity_days[activity_date] = activity_days.get(activity_date, 0.0) + tss_value
    return activity_days


def _format_dashboard_sport_label(sport: Any) -> str:
    """Return a compact reader-facing sport label for Dashboard cards."""
    return sport_label(sport)


def build_dashboard_summary(
    state: Any,
    current_status: dict[str, Any],
    latest_training_status: dict[str, Any],
    activities_df: pd.DataFrame,
    *,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Build a testable command-center summary for Dashboard V2."""
    today = reference_date or datetime.now().date()
    goal_plan = get_dashboard_goal_plan(state)
    plan_lookup = build_plan_day_lookup(goal_plan)
    activity_tss_by_day = build_activity_day_tss(activities_df)
    checkpoint_summary = summarize_planning_checkpoint(
        getattr(state, "latest_planning_checkpoint", None)
    )

    readiness_value = current_status.get("readiness")
    if readiness_value is None or pd.isna(readiness_value):
        readiness_value = latest_training_status.get("training_readiness", 0)
    try:
        readiness_number = max(0.0, min(100.0, float(readiness_value or 0.0)))
    except (TypeError, ValueError):
        readiness_number = 0.0
    tsb_value = float(current_status.get("tsb") or 0.0)
    ctl_value = float(current_status.get("ctl") or 0.0)
    hrv_value = current_status.get("hrv") or latest_training_status.get("hrv")
    if current_status.get("state_label") and current_status.get("tone"):
        state_label = str(current_status["state_label"])
        tone = str(current_status["tone"])
    elif current_status.get("critical_status"):
        state_label = str(current_status["critical_status"])
        tone = "danger"
    elif readiness_number >= 75 and tsb_value > -10:
        state_label = "Готов к работе"
        tone = "success"
    elif tsb_value < -20:
        state_label = "Нужна разгрузка"
        tone = "warning"
    else:
        state_label = "Контролируемая нагрузка"
        tone = "neutral"

    today_plan = plan_lookup.get(today)
    if today_plan is None:
        workout = {
            "title": "План на сегодня не найден",
            "subtitle": "Откройте Planning, если нужно уточнить ближайшие тренировки.",
            "tss": 0,
            "sport": "—",
            "sport_key": "other",
            "sport_label": "—",
            "action": "planning",
            "button": "Открыть Planning",
        }
    elif today_plan["total_tss"] <= 0:
        workout = {
            "title": "Сегодня восстановление",
            "subtitle": "План не ставит тренировочную нагрузку на сегодня.",
            "tss": 0,
            "sport": "отдых",
            "sport_key": "off",
            "sport_label": "отдых",
            "action": "planning",
            "button": "Посмотреть неделю",
        }
    else:
        duration = today_plan["duration_minutes"]
        duration_label = f"{duration} мин · " if duration > 0 else ""
        today_sport_label = _format_dashboard_sport_label(today_plan["sport"])
        workout = {
            "title": today_plan["name"],
            "subtitle": (
                f"{duration_label}{today_sport_label} · "
                f"{_format_tss_value(today_plan['total_tss'])} TSS"
            ),
            "tss": int(round(today_plan["total_tss"])),
            "sport": today_sport_label,
            "sport_key": normalize_sport_key(today_plan["sport"]),
            "sport_label": today_sport_label,
            "action": "planning",
            "button": "Открыть план",
        }

    week_start = today - timedelta(days=today.weekday())
    week_days = [week_start + timedelta(days=offset) for offset in range(7)]
    planned_week_tss = sum(
        float(plan_lookup.get(day, {}).get("total_tss") or 0.0) for day in week_days
    )
    actual_week_tss = sum(float(activity_tss_by_day.get(day, 0.0)) for day in week_days)
    remaining_tss = max(0.0, planned_week_tss - actual_week_tss)
    forecast_tss = actual_week_tss + sum(
        float(plan_lookup.get(day, {}).get("total_tss") or 0.0)
        for day in week_days
        if day >= today
    )
    week_status = "по плану"
    if (
        planned_week_tss > 0
        and actual_week_tss < planned_week_tss * 0.55
        and today.weekday() >= 4
    ):
        week_status = "риск отставания"
    elif planned_week_tss > 0 and actual_week_tss >= planned_week_tss:
        week_status = "цель недели закрыта"

    next_days = []
    for offset in range(7):
        day = today + timedelta(days=offset)
        planned = plan_lookup.get(day)
        actual_tss = activity_tss_by_day.get(day, 0.0)
        if planned is None:
            label = "нет плана"
            tss = 0
            sport = "—"
            sport_key = "other"
            status = "empty"
        else:
            tss = int(round(float(planned.get("total_tss") or 0.0)))
            sport_key = normalize_sport_key(planned.get("sport") or "—")
            sport = _format_dashboard_sport_label(planned.get("sport") or "—")
            if tss <= 0:
                label = "отдых"
                status = "rest"
            elif actual_tss > 0:
                label = "есть факт"
                status = "done"
            else:
                label = "запланировано"
                status = "planned"
        next_days.append(
            {
                "date": day.isoformat(),
                "label": format_date_label(day, "weekday_short"),
                "status": status,
                "status_label": label,
                "sport": sport,
                "sport_key": sport_key,
                "sport_label": sport,
                "tss": tss,
            }
        )

    if checkpoint_summary is None:
        plan = {
            "title": "Активный план не найден",
            "subtitle": "Соберите план, чтобы Dashboard показывал прогресс к цели.",
            "status": "no_plan",
            "button": "Собрать план",
        }
    else:
        plan = {
            "title": checkpoint_summary["title"],
            "subtitle": f"{checkpoint_summary['plan_adjustment_label']} · пик {checkpoint_summary['peak_tss']} TSS",
            "status": "active",
            "button": "Открыть Planning",
        }
        if checkpoint_summary.get("execution_weekly_review"):
            plan["subtitle"] = str(
                checkpoint_summary["execution_weekly_review"]["headline"]
            )

    next_step = choose_primary_next_step(state, current_status)
    return {
        "today": {
            "date": today.isoformat(),
            "date_label": format_date_label(today, "weekday_short"),
            "state_label": state_label,
            "tone": tone,
            "readiness": int(round(readiness_number)),
            "tsb": round(tsb_value, 1),
            "ctl": round(ctl_value, 1),
            "hrv": hrv_value,
        },
        "workout": workout,
        "week": {
            "planned_tss": int(round(planned_week_tss)),
            "actual_tss": int(round(actual_week_tss)),
            "remaining_tss": int(round(remaining_tss)),
            "forecast_tss": int(round(forecast_tss)),
            "status": week_status,
        },
        "next_days": next_days,
        "plan": plan,
        "next_action": next_step,
        "signals": current_status.get("signals"),
    }


def calculate_current_status(
    activities_df: pd.DataFrame,
    hrv_df: pd.DataFrame,
    sleep_df: pd.DataFrame,
    training_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build dashboard status from explicitly supplied dataframes."""

    signals = assemble_signals(
        activities_df=activities_df,
        hrv_df=hrv_df,
        sleep_df=sleep_df,
        training_status=training_status,
    )
    status = current_status_from_signals(signals)

    logger.debug("Текущий статус: %s", status)
    return status


def get_latest_training_status(database: Any) -> dict[str, Any]:
    training_status_df = database.get_training_status_history(days=30)
    if isinstance(training_status_df, pd.DataFrame) and not training_status_df.empty:
        return training_status_df.sort_values("date", ascending=False).iloc[0].to_dict()
    return {}


def choose_primary_next_step(
    state: Any,
    current_status: dict[str, Any],
) -> dict[str, str]:
    summary = build_dashboard_explainability_summary(state, current_status)
    ai_ready = getattr(state, "ai_coach", None) is not None

    if summary["focus"] == "recovery":
        return {
            "icon": summary["icon"],
            "title": summary["title"],
            "button": summary["dashboard_button"],
            "desc": summary["description"],
            "reason": summary["reason"],
            "action": "recovery_plan",
        }

    if not ai_ready:
        return {
            "icon": "🤖",
            "title": "Подготовьте AI коуча",
            "button": "Открыть AI коучинг",
            "desc": "Данные уже на месте. Следующий полезный шаг — открыть AI coaching и получить персональную интерпретацию текущего состояния.",
            "reason": "Если провайдер уже настроен, коуч подключится автоматически. Иначе вы сразу попадёте в нужное место для настройки.",
            "action": "ai_chat",
        }

    return {
        "icon": summary["icon"],
        "title": "Получите персональную рекомендацию"
        if summary["focus"] == "form_today"
        else summary["title"],
        "button": summary["dashboard_button"],
        "desc": summary["description"],
        "reason": summary["reason"],
        "action": "ai_chat",
    }


def build_dashboard_explainability_summary(
    state: Any,
    current_status: dict[str, Any],
) -> dict[str, Any]:
    hrv_val = current_status.get("hrv")
    recovery_state = None
    try:
        if hrv_val and float(hrv_val) < 30:
            recovery_state = "poor"
    except (TypeError, ValueError):
        recovery_state = None

    return build_coach_explainability_summary(
        tsb=current_status.get("tsb"),
        ctl=current_status.get("ctl"),
        atl=current_status.get("atl"),
        readiness=current_status.get("readiness"),
        recovery_state=recovery_state,
        goal_plan=getattr(state, "resolved_goal_plan_context", None),
        execution_feedback=getattr(state, "latest_execution_feedback", None),
    )

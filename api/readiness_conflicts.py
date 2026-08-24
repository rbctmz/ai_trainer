"""Сборка отчёта конфликтов «готовность × плановая сессия» из локальной БД.

Обвязка над чистой логикой models/readiness_conflicts.py (issue #141):
готовность — models/readiness.py с дефолтной свежестью (значения старше
2 дней выпадают: детектор, тревожащий на несвежих данных, ложно-положителен),
план — активный planning checkpoint. Базовый горизонт 3 дня расширяется до
ближайшей quality- или структурированной high-load сессии в пределах 7 дней
(issues #152/#315). Отчёт едет в SSE meta коуча.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from api.planning_service import get_active_plan
from data.database import Database
from models.readiness import LOAD_METRICS_WINDOW_DAYS, compute_readiness_today
from models.readiness_conflicts import (
    DEFAULT_HORIZON_DAYS,
    MAX_QUALITY_LOOKAHEAD_DAYS,
    detect_readiness_conflicts,
    resolve_effective_horizon,
    upcoming_plan_sessions,
)


def build_readiness_conflict_report(
    db: Database,
    *,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    max_quality_lookahead_days: int = MAX_QUALITY_LOOKAHEAD_DAYS,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or datetime.now().date()

    try:
        sleep_df = db.get_sleep_data(36500)
        hrv_df = db.get_hrv_data(36500)
        health_df = db.get_daily_health(36500)
        training_df = db.get_training_status_history(36500)
        activities_df = db.get_activities(LOAD_METRICS_WINDOW_DAYS)
    except Exception:
        sleep_df = hrv_df = health_df = training_df = activities_df = None

    readiness = compute_readiness_today(
        sleep_df,
        hrv_df,
        health_df,
        training_df,
        activities_df,
        today=today,
    )

    goal_plan = None
    try:
        goal_plan = get_active_plan(db)
    except Exception:
        goal_plan = None

    horizon_policy = resolve_effective_horizon(
        goal_plan,
        today=today,
        base_horizon_days=horizon_days,
        max_horizon_days=max_quality_lookahead_days,
    )
    effective_horizon_days = horizon_policy["effective_horizon_days"]
    sessions = upcoming_plan_sessions(
        goal_plan,
        today=today,
        horizon_days=effective_horizon_days,
    )
    report = detect_readiness_conflicts(
        readiness,
        sessions,
        today=today,
        horizon_days=effective_horizon_days,
    )
    report.update(
        {
            "base_horizon_days": horizon_policy["base_horizon_days"],
            "lookahead_policy": horizon_policy["lookahead_policy"],
            "horizon_extended_for_quality": horizon_policy["extended_for_quality"],
            "quality_lookahead_session": horizon_policy["quality_session"],
            "horizon_extended_for_salience": horizon_policy[
                "extended_for_salience"
            ],
            "salience_lookahead_session": horizon_policy["salience_session"],
        }
    )

    if goal_plan is None and not report["data_gap"]:
        report["reason"] = "Нет активного плана — сверять готовность не с чем."
    return report

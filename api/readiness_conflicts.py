"""Сборка отчёта конфликтов «готовность × плановая сессия» из локальной БД.

Обвязка над чистой логикой models/readiness_conflicts.py (issue #141):
готовность — models/readiness.py с дефолтной свежестью (значения старше
2 дней выпадают: детектор, тревожащий на несвежих данных, ложно-положителен),
план — активный planning checkpoint. Отчёт едет в SSE meta коуча.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from api.planning_service import get_active_plan
from data.database import Database
from models.readiness import LOAD_METRICS_WINDOW_DAYS, compute_readiness_today
from models.readiness_conflicts import (
    DEFAULT_HORIZON_DAYS,
    detect_readiness_conflicts,
    upcoming_plan_sessions,
)


def build_readiness_conflict_report(
    db: Database,
    *,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> dict[str, Any]:
    today = datetime.now().date()

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

    sessions = upcoming_plan_sessions(goal_plan, today=today, horizon_days=horizon_days)
    report = detect_readiness_conflicts(
        readiness, sessions, today=today, horizon_days=horizon_days
    )

    if goal_plan is None and not report["data_gap"]:
        report["reason"] = "Нет активного плана — сверять готовность не с чем."
    return report

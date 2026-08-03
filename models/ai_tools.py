"""
Система инструментов для AI тренера (аналог MCP сервера)
Позволяет AI делать динамические запросы к базе данных
"""

import json
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from api import planning_service
from data.database import Database
from models.banister import tsb_zone
from models.hrv_analyzer import HRVAnalyzer
from models.plan_events import normalized_events
from models.planning_checkpoints import (
    NON_ACTIONABLE_PLAN_ADJUSTMENTS,
    build_planning_checkpoint,
    restore_goal_plan_from_checkpoint,
    with_checkpoint_provenance,
)
from models.coach_constraints import apply_constraints_to_goal_plan
from models.readiness import LOAD_METRICS_WINDOW_DAYS as COACH_LOAD_METRICS_WINDOW_DAYS
from models.readiness import compute_readiness_today
from models.signals_engine import assemble_signals
from utils.product_semantics import (
    TODAY_PARTIAL_NOTE_RU,
    format_date_label,
    is_today,
    normalize_training_status_key,
    normalize_sport_key,
    sport_label,
    training_status_label,
    trend_label,
)


def _localized_sports_distribution(values) -> Dict[str, int]:
    distribution: Dict[str, int] = {}
    for raw_sport, count in dict(values).items():
        label = sport_label(raw_sport)
        distribution[label] = distribution.get(label, 0) + int(count)
    return distribution


# _interpret_tsb used its own 5-bucket TSB split (10/0/-15/-30) against the
# canonical tsb_zone()'s 4 (-20/-10/+10). "хорошая форма" (the old
# 0 < tsb <= 10 bucket) is retired here and folds into "поддержание".
# Intentional consequence of unification (#63).
_TSB_TONE_TO_INTERPRETATION = {
    "success": "пиковая форма",
    "neutral": "поддержание",
    "warning": "накопление",
    "danger": "перегрузка",
}


def _latest_date_iso(df: pd.DataFrame) -> str | None:
    if df.empty or "date" not in df.columns:
        return None
    try:
        latest = pd.to_datetime(df["date"]).max()
    except Exception:
        return None
    if pd.isna(latest):
        return None
    return latest.strftime("%Y-%m-%d")


def _is_actionable_plan_adjustment(
    adjustment: Dict[str, Any],
    rows: List[Dict[str, Any]],
) -> bool:
    """Return whether an adjustment preview represents a real pending mutation."""
    status = str(adjustment.get("status") or "").strip().lower()
    label = str(adjustment.get("label") or "").strip()
    missed_sessions = int(adjustment.get("missed_sessions") or 0)
    try:
        completion_share = float(adjustment.get("completion_share") or 0.0)
    except (TypeError, ValueError):
        completion_share = 0.0

    changed_outcomes = {
        "missed",
        "skipped",
        "reduced",
        "unavailable",
    }
    has_changed_rows = any(
        str(row.get("outcome") or "").strip().lower() in changed_outcomes
        for row in rows
    )

    if status in {"skipped", "reduced", "unavailable"} or has_changed_rows:
        return True

    return not (
        status in {"completed", "none", ""}
        and missed_sessions == 0
        and completion_share >= 0.99
        and label in NON_ACTIONABLE_PLAN_ADJUSTMENTS
    )


class AITools:
    """Система инструментов для AI тренера"""
    
    def __init__(self, database: Database):
        self.db = database
        self.hrv_analyzer = HRVAnalyzer()
        
        # Регистрируем доступные инструменты
        self.tools = {
            "get_activities": self.get_activities,
            "get_hrv_data": self.get_hrv_data,
            "get_activity_stats": self.get_activity_stats,
            "get_performance_metrics": self.get_performance_metrics,
            "get_recent_activities": self.get_recent_activities,
            "analyze_training_load": self.analyze_training_load,
            "analyze_hrv_trends": self.analyze_hrv_trends,
            "compare_periods": self.compare_periods,
            "get_activity_by_sport": self.get_activity_by_sport,
            "calculate_weekly_stats": self.calculate_weekly_stats,
            "find_best_performances": self.find_best_performances,
            "analyze_recovery_state": self.analyze_recovery_state,
            "get_activities_by_date_range": self.get_activities_by_date_range,
            "get_sleep_data": self.get_sleep_data,
            "analyze_sleep_patterns": self.analyze_sleep_patterns,
            "get_sleep_stats": self.get_sleep_stats,
            "get_training_status": self.get_training_status,
            "analyze_training_status": self.analyze_training_status,
            "get_daily_health_stats": self.get_daily_health_stats,
            "get_active_plan": self.get_active_plan,
            "get_upcoming_workouts": self.get_upcoming_workouts,
            "propose_plan_build": self.propose_plan_build,
            "propose_plan_adjustment": self.propose_plan_adjustment,
            "create_plan_constraint": self.create_plan_constraint,
            "get_readiness_today": self.get_readiness_today,
            "get_pending_proposals": self.get_pending_proposals,
        }
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """JSON-схемы инструментов — единый реестр (Issue #190).

        Один источник для двух потребителей: нативного tools API провайдеров
        (OpenAI-совместимые/Anthropic адаптеры транслируют эти схемы в свой
        формат) и маркерного пути, чьи текстовые описания в промпте выводятся
        из ``description`` этих же схем. Параметры типизированы, чтобы вход
        валидировался контрактно, а не regex-парсером свободного текста.
        """

        def _params(
            properties: Optional[Dict[str, Any]] = None,
            required: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            return {
                "type": "object",
                "properties": properties or {},
                "required": list(required or []),
            }

        def _days(default: int) -> Dict[str, Any]:
            return {
                "days": {
                    "type": "integer",
                    "default": default,
                    "description": "Период в днях",
                }
            }

        return [
            {
                "name": "get_activities",
                "description": "Получить список активностей за период (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "get_hrv_data",
                "description": "Получить HRV данные за период (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "get_activity_stats",
                "description": "Получить статистику по активностям (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "get_performance_metrics",
                "description": (
                    "Получить метрики производительности (CTL/ATL/TSB). "
                    "days задаёт период отчёта/тренда; CTL/ATL/TSB всегда считаются на стабильном окне"
                ),
                "parameters": _params(_days(30)),
            },
            {
                "name": "get_recent_activities",
                "description": "Получить последние N активностей (limit=10)",
                "parameters": _params(
                    {
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "description": "Сколько последних активностей вернуть",
                        }
                    }
                ),
            },
            {
                "name": "analyze_training_load",
                "description": "Анализ тренировочной нагрузки за период (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "analyze_hrv_trends",
                "description": "Анализ трендов HRV (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "compare_periods",
                "description": "Сравнить два периода тренировок (period1_days=30, period2_days=30)",
                "parameters": _params(
                    {
                        "period1_days": {
                            "type": "integer",
                            "default": 30,
                            "description": "Длина недавнего периода в днях",
                        },
                        "period2_days": {
                            "type": "integer",
                            "default": 30,
                            "description": "Длина предыдущего периода в днях",
                        },
                    }
                ),
            },
            {
                "name": "get_activity_by_sport",
                "description": "Получить активности по виду спорта (sport='cycling', days=30)",
                "parameters": _params(
                    {
                        "sport": {
                            "type": "string",
                            "description": "Вид спорта: cycling/running/swimming",
                        },
                        **_days(30),
                    },
                    required=["sport"],
                ),
            },
            {
                "name": "calculate_weekly_stats",
                "description": "Рассчитать недельную статистику (weeks=4)",
                "parameters": _params(
                    {
                        "weeks": {
                            "type": "integer",
                            "default": 4,
                            "description": "Количество последних недель",
                        }
                    }
                ),
            },
            {
                "name": "find_best_performances",
                "description": "Найти лучшие результаты по метрикам (metric='tss', limit=10)",
                "parameters": _params(
                    {
                        "metric": {
                            "type": "string",
                            "default": "tss",
                            "description": "Метрика ранжирования: tss/distance/duration/avg_hr",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "description": "Сколько результатов вернуть",
                        },
                    }
                ),
            },
            {
                "name": "analyze_recovery_state",
                "description": "Проанализировать текущее состояние восстановления",
                "parameters": _params(),
            },
            {
                "name": "get_activities_by_date_range",
                "description": (
                    "Получить активности за конкретный период "
                    "(start_date='2025-05-01', end_date='2025-05-31')"
                ),
                "parameters": _params(
                    {
                        "start_date": {
                            "type": "string",
                            "description": "Начало периода, YYYY-MM-DD",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Конец периода, YYYY-MM-DD",
                        },
                    },
                    required=["start_date", "end_date"],
                ),
            },
            {
                "name": "get_sleep_data",
                "description": "Получить данные сна за период (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "analyze_sleep_patterns",
                "description": "Анализ паттернов и качества сна (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "get_sleep_stats",
                "description": "Получить статистику сна (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "get_training_status",
                "description": "Получить историю статуса тренированности и readiness (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "analyze_training_status",
                "description": "Глубокий анализ статуса тренированности и нагрузки (days=30)",
                "parameters": _params(_days(30)),
            },
            {
                "name": "get_daily_health_stats",
                "description": (
                    "Получить ежедневные показатели здоровья (шаги, ЧСС, калории) за период (days=30)"
                ),
                "parameters": _params(_days(30)),
            },
            {
                "name": "get_active_plan",
                "description": (
                    "Получить активный тренировочный план: цель, старты с приоритетами, "
                    "дату главного старта, фазы, недельные TSS-таргеты, итоговый TSS и пик, "
                    "а также текущую неделю (current_week) и оставшиеся недели до старта, "
                    "пересчитанные от сегодняшней даты"
                ),
                "parameters": _params(),
            },
            {
                "name": "get_upcoming_workouts",
                "description": "Получить ближайшие плановые тренировки из активного плана (days=7)",
                "parameters": _params(_days(7)),
            },
            {
                "name": "propose_plan_build",
                "description": (
                    "Предложить собрать новый план подготовки. Параметры: goal_type (Триатлон/Бег/Вело/Плавание), "
                    "distance (Sprint/Olympic/Half/Full или 5K/10K/21K/42K), event_date (YYYY-MM-DD), "
                    "available_hours (часов в неделю), available_days (необязательно, через запятую: mon,tue,...)."
                ),
                "parameters": _params(
                    {
                        "goal_type": {
                            "type": "string",
                            "description": "Триатлон/Бег/Вело/Плавание",
                        },
                        "distance": {
                            "type": "string",
                            "description": "Sprint/Olympic/Half/Full или 5K/10K/21K/42K",
                        },
                        "event_date": {
                            "type": "string",
                            "description": "Дата старта, YYYY-MM-DD",
                        },
                        "available_hours": {
                            "type": "number",
                            "description": "Доступно часов в неделю",
                        },
                        "available_days": {
                            "type": "string",
                            "description": "Необязательно: дни недели через запятую (mon,tue,...)",
                        },
                    },
                    required=["goal_type", "distance", "event_date", "available_hours"],
                ),
            },
            {
                "name": "propose_plan_adjustment",
                "description": (
                    "Предложить корректировку активного плана по факту выполнения недели. "
                    "Параметры: weeks (целое, по умолчанию 1)."
                ),
                "parameters": _params(
                    {
                        "weeks": {
                            "type": "integer",
                            "default": 1,
                            "description": "Сколько последних недель учитывать",
                        }
                    }
                ),
            },
            {
                "name": "create_plan_constraint",
                "description": (
                    "Сохранить durable-ограничение на дату и сразу применить его к активному плану, "
                    "если он есть. Используй только при явной фразе пользователя вроде 'я болею завтра', "
                    "'не могу тренироваться 2026-07-10', 'удали тренировку в этот день'. "
                    "Параметры: date (YYYY-MM-DD/today/tomorrow/сегодня/завтра), "
                    "kind (sick/unavailable/forced_rest/manual_delete/disabled_plan_day или русские синонимы), "
                    "note (необязательно)."
                ),
                "parameters": _params(
                    {
                        "date": {
                            "type": "string",
                            "description": "YYYY-MM-DD или today/tomorrow/сегодня/завтра",
                        },
                        "kind": {
                            "type": "string",
                            "default": "unavailable",
                            "description": (
                                "sick/unavailable/forced_rest/manual_delete/disabled_plan_day "
                                "или русские синонимы"
                            ),
                        },
                        "note": {
                            "type": "string",
                            "description": "Необязательная заметка",
                        },
                    },
                    required=["date", "kind"],
                ),
            },
            {
                "name": "get_readiness_today",
                "description": (
                    "Получить КАНОНИЧЕСКИЙ снимок готовности на сегодня (тот же, что "
                    "в сайдбаре «Сигналы»): fusion HRV/RHR/сна/Garmin readiness/TSB "
                    "с evidence, драйверами и confidence, привязанный к текущей дате. "
                    "Вызывай ОБЯЗАТЕЛЬНО перед любой рекомендацией «на сегодня/завтра»."
                ),
                "parameters": _params(),
            },
            {
                "name": "get_pending_proposals",
                "description": (
                    "Получить активные (pending) предложения агентного контура "
                    "(recovery replan, корректировки плана) со статусом, датами и сутью. "
                    "Если предложение висит — не противоречь ему, сошлись на него."
                ),
                "parameters": _params(),
            },
        ]

    def get_available_tools(self) -> Dict[str, str]:
        """Имя → описание; выводится из единого реестра схем (Issue #190)."""
        return {
            schema["name"]: schema["description"] for schema in self.get_tool_schemas()
        }
    
    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Выполняет инструмент с параметрами"""
        if tool_name not in self.tools:
            return {
                "error": f"Инструмент '{tool_name}' не найден",
                "available_tools": list(self.tools.keys())
            }
        
        try:
            result = self.tools[tool_name](**kwargs)
            if isinstance(result, dict) and result.get("success") is False and result.get("error"):
                return {
                    "success": False,
                    "tool": tool_name,
                    "parameters": kwargs,
                    "error": str(result.get("error")),
                }
            return {
                "success": True,
                "tool": tool_name,
                "parameters": kwargs,
                "result": result
            }
        except Exception as e:
            return {
                "error": f"Ошибка выполнения инструмента '{tool_name}': {str(e)}",
                "parameters": kwargs
            }
    
    # === ИНСТРУМЕНТЫ ===
    
    def get_activities(self, days: int = 30) -> Dict[str, Any]:
        """Получить активности за период"""
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": "Нет активностей за указанный период", "count": 0}
        
        # Конвертируем в удобный формат
        activities = []
        for _, row in df.iterrows():
            raw_sport = row.get("sport", "unknown")
            localized_sport = sport_label(raw_sport)
            activity = {
                "date": row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else None,
                "date_label": format_date_label(row.get("date")),
                "sport": normalize_sport_key(raw_sport),
                "sport_label": localized_sport,
                "duration_minutes": float(row.get("duration_minutes", 0)) if pd.notna(row.get("duration_minutes")) else 0,
                "distance_km": float(row.get("distance_km", 0)) if pd.notna(row.get("distance_km")) else 0,
                "tss": float(row.get("tss", 0)) if pd.notna(row.get("tss")) else 0,
                "avg_hr": float(row.get("avg_hr", 0)) if pd.notna(row.get("avg_hr")) else 0,
                "avg_power": float(row.get("avg_power", 0)) if pd.notna(row.get("avg_power")) else 0
            }
            activities.append(activity)
        
        return {
            "count": len(activities),
            "period_days": days,
            "activities": activities[:20]  # Ограничиваем для читаемости
        }
    
    def get_hrv_data(self, days: int = 30) -> Dict[str, Any]:
        """Получить HRV данные за период"""
        df = self.db.get_hrv_data(days)
        
        if df.empty:
            return {"message": "Нет HRV данных за указанный период", "count": 0}
        
        hrv_data = []
        for _, row in df.iterrows():
            hrv_entry = {
                "date": row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else None,
                "rmssd": float(row.get("rmssd", 0)) if pd.notna(row.get("rmssd")) else 0,
                "stress_score": float(row.get("stress_score", 0)) if pd.notna(row.get("stress_score")) else None,
                "recovery_score": float(row.get("recovery_score", 0)) if pd.notna(row.get("recovery_score")) else None
            }
            hrv_data.append(hrv_entry)
        
        return {
            "count": len(hrv_data),
            "period_days": days,
            "avg_rmssd": df["rmssd"].mean(),
            "current_rmssd": float(df.iloc[0]["rmssd"]) if len(df) > 0 else 0,
            "data": hrv_data[:20]  # Последние 20 записей
        }
    
    def get_activity_stats(self, days: int = 30) -> Dict[str, Any]:
        """Получить статистику по активностям"""
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": "Нет данных для статистики", "period_days": days}
        
        return {
            "period_days": days,
            "total_activities": len(df),
            "total_duration_hours": float(df["duration_minutes"].sum() / 60),
            "total_distance_km": float(df["distance_km"].sum()) if "distance_km" in df.columns else 0,
            "total_tss": float(df["tss"].sum()) if "tss" in df.columns else 0,
            "avg_tss_per_session": float(df["tss"].mean()) if "tss" in df.columns else 0,
            "activities_per_week": float(len(df) * 7 / days),
            "sports_distribution": (
                _localized_sports_distribution(df["sport"].value_counts().to_dict())
                if "sport" in df.columns
                else {}
            ),
            "avg_duration_minutes": float(df["duration_minutes"].mean()),
            "avg_heart_rate": float(df["avg_hr"].mean()) if "avg_hr" in df.columns and not df["avg_hr"].isna().all() else 0
        }
    
    def get_performance_metrics(self, days: int = 30) -> Dict[str, Any]:
        """Получить метрики производительности (CTL/ATL/TSB).

        `days` влияет только на отчётный/трендовый контекст. CTL/ATL/TSB
        считаются на стабильном окне, чтобы LLM не меняла EWMA-метрики
        произвольными параметрами tool call.
        """
        report_days = max(1, int(days or 30))
        metrics_window_days = COACH_LOAD_METRICS_WINDOW_DAYS
        report_df = self.db.get_activities(report_days)
        metrics_df = self.db.get_activities(metrics_window_days)

        if metrics_df.empty:
            return {
                "message": "Нет данных для расчета метрик производительности",
                "data_through": None,
                "computed_for": date.today().isoformat(),
            }

        # Issue #231: anchor CTL/ATL/TSB to today so a rest morning shows the
        # fresh "today" TSB (matching the canonical readiness sidebar), not a
        # value frozen at the last activity date (second instance of #139).
        today = date.today()
        signals = assemble_signals(activities_df=metrics_df, as_of=today)
        load = signals["load"]
        tss_data = []

        trend_df = report_df if not report_df.empty else metrics_df
        for _, row in trend_df.iterrows():
            tss_val = row.get("tss", 0)
            if pd.isna(tss_val):
                tss_val = 0
            tss_data.append(float(tss_val))

        ctl = float(load["ctl"])
        atl = float(load["atl"])
        tsb = float(load["tsb"])
        data_through = _latest_date_iso(metrics_df)
        computed_for = today.isoformat()

        return {
            "ctl": ctl,
            "atl": atl,
            "tsb": tsb,
            "report_period_days": report_days,
            "metrics_window_days": metrics_window_days,
            # data_through = last activity date; computed_for = today (the
            # anchor). The model must never read data_through as "today" (#231).
            "data_through": data_through,
            "computed_for": computed_for,
            "as_of_date": computed_for,
            "form_state": self._interpret_tsb(tsb),
            "fitness_trend": self._calculate_fitness_trend(tss_data),
            "fatigue_level": self._interpret_atl(atl),
            "signals": signals,
            "signal_source": signals["source"],
        }
    
    def get_readiness_today(self) -> Dict[str, Any]:
        """Канонический снимок готовности на сегодня (Issue #231).

        Тот же `compute_readiness_today`, что питает сайдбар «Сигналы» и гейт
        конфликтов — чтобы чат не расходился с контуром по readiness/TSB.
        """
        today = date.today()
        try:
            sleep_df = self.db.get_sleep_data(36500)
            hrv_df = self.db.get_hrv_data(36500)
            health_df = self.db.get_daily_health(36500)
            training_df = self.db.get_training_status_history(36500)
            activities_df = self.db.get_activities(COACH_LOAD_METRICS_WINDOW_DAYS)
        except Exception as exc:
            return {"success": False, "error": f"Нет данных готовности: {exc}"}

        snapshot = compute_readiness_today(
            sleep_df, hrv_df, health_df, training_df, activities_df, today=today
        )
        if not snapshot:
            return {
                "success": True,
                "computed_for": today.isoformat(),
                "message": "Недостаточно данных для расчёта готовности",
            }
        return {"success": True, "computed_for": today.isoformat(), "readiness": snapshot}

    def get_pending_proposals(self) -> Dict[str, Any]:
        """Активные предложения контура (pending) — recovery replan и правки плана.

        Issue #231: чат обязан видеть висящее предложение, чтобы не советовать
        выполнять день, который контур уже предлагает разгрузить.
        """
        try:
            rows = self.db.get_coach_proposals(days=14, status="pending") or []
        except Exception as exc:
            return {"success": False, "error": f"Не удалось прочитать предложения: {exc}"}

        proposals = []
        for row in rows:
            item = dict(row) if isinstance(row, dict) else {}
            proposals.append(
                {
                    "id": item.get("id"),
                    "date": str(item.get("date") or "")[:10],
                    "action": item.get("action"),
                    "status": item.get("status"),
                    "preview": item.get("preview") or item.get("preview_json"),
                }
            )
        return {
            "success": True,
            "computed_for": date.today().isoformat(),
            "count": len(proposals),
            "pending_proposals": proposals,
        }

    def get_recent_activities(self, limit: int = 10) -> Dict[str, Any]:
        """Получить последние N активностей"""
        df = self.db.get_activities(30)  # Берем за 30 дней
        
        if df.empty:
            return {"message": "Нет недавних активностей", "count": 0}
        
        recent = df.head(limit)
        activities = []
        
        for _, row in recent.iterrows():
            raw_sport = row.get("sport", "unknown")
            localized_sport = sport_label(raw_sport)
            date_label = format_date_label(row.get("date"), "weekday_short")
            today_partial = is_today(row.get("date"))
            if today_partial:
                date_label = f"{date_label} {TODAY_PARTIAL_NOTE_RU}"
            activity = {
                "date": row["date"].strftime("%Y-%m-%d"),
                "date_label": date_label,
                "is_today_partial": today_partial,
                "sport": normalize_sport_key(raw_sport),
                "sport_label": localized_sport,
                "duration_minutes": float(row.get("duration_minutes", 0)),
                "distance_km": float(row.get("distance_km", 0)) if pd.notna(row.get("distance_km")) else 0,
                "tss": float(row.get("tss", 0)) if pd.notna(row.get("tss")) else 0,
                "description": (
                    f"{localized_sport} — {row.get('duration_minutes', 0):.0f} мин, "
                    f"TSS {row.get('tss', 0):.0f}"
                ),
            }
            activities.append(activity)
        
        return {
            "count": len(activities),
            "activities": activities
        }
    
    def analyze_training_load(self, days: int = 30) -> Dict[str, Any]:
        """Анализ тренировочной нагрузки"""
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": "Нет данных для анализа нагрузки"}
        
        # Преобразуем дату в datetime если нужно
        df["date"] = pd.to_datetime(df["date"])
        
        # Анализ по неделям
        df["week"] = df["date"].dt.isocalendar().week
        weekly_stats = df.groupby("week").agg({
            "tss": ["sum", "mean", "count"],
            "duration_minutes": "sum"
        }).round(2)
        
        weekly_data = []
        for week, stats in weekly_stats.iterrows():
            weekly_data.append({
                "week": int(week),
                "total_tss": float(stats[("tss", "sum")]),
                "avg_tss": float(stats[("tss", "mean")]),
                "session_count": int(stats[("tss", "count")]),
                "total_duration": float(stats[("duration_minutes", "sum")])
            })
        
        return {
            "period_days": days,
            "weekly_breakdown": weekly_data,
            "load_trend": self._calculate_load_trend(df),
            "intensity_distribution": self._analyze_intensity_distribution(df)
        }
    
    def analyze_hrv_trends(self, days: int = 30) -> Dict[str, Any]:
        """Анализ трендов HRV"""
        df = self.db.get_hrv_data(days)
        
        if df.empty:
            return {"message": "Нет HRV данных для анализа трендов"}
        
        if len(df) < 7:
            return {"message": "Недостаточно данных для анализа трендов (нужно минимум 7 дней)"}
        
        # Анализ тренда
        x = np.arange(len(df))
        trend_coefficient = np.polyfit(x, df["rmssd"], 1)[0]
        
        # Недавние vs базовые значения
        recent_avg = df.head(7)["rmssd"].mean()
        baseline_avg = df["rmssd"].median()
        trend_direction = "improving" if trend_coefficient > 0 else "declining"
        
        return {
            "period_days": days,
            "data_points": len(df),
            "current_rmssd": float(df.iloc[0]["rmssd"]),
            "recent_avg_7days": float(recent_avg),
            "baseline_median": float(baseline_avg),
            "trend_direction": trend_direction,
            "trend_direction_label": trend_label(trend_direction),
            "trend_slope": float(trend_coefficient),
            "recovery_state": self._assess_recovery_state(recent_avg, baseline_avg),
            "variability": float(df["rmssd"].std())
        }
    
    def compare_periods(self, period1_days: int = 30, period2_days: int = 30) -> Dict[str, Any]:
        """Сравнить два периода тренировок"""
        try:
            now = pd.Timestamp.now().normalize()
            window_days = period1_days + period2_days
            
            # Первый период (недавний)
            df1 = self.db.get_activities(period1_days)
            if not df1.empty and "date" in df1.columns:
                df1 = df1.copy()
                df1["date"] = pd.to_datetime(df1["date"], errors="coerce").dt.normalize()
            
            # Получаем активности за окно, чтобы выделить второй период
            all_activities = self.db.get_activities(window_days)
            if not all_activities.empty and "date" in all_activities.columns:
                all_activities = all_activities.copy()
                all_activities["date"] = pd.to_datetime(all_activities["date"], errors="coerce").dt.normalize()
            
            previous_period_end = now - pd.Timedelta(days=period1_days)
            previous_period_start = previous_period_end - pd.Timedelta(days=period2_days)
            
            if not all_activities.empty:
                mask = (
                    (all_activities["date"] >= previous_period_start)
                    & (all_activities["date"] < previous_period_end)
                )
                df2 = all_activities.loc[mask].copy()
            else:
                df2 = pd.DataFrame()
            
            def get_period_stats(df: pd.DataFrame, period_name: str, period_length: int) -> Dict[str, Any]:
                if df.empty:
                    return {"period": period_name, "no_data": True}
                
                total_tss = float(df["tss"].sum()) if "tss" in df.columns else 0.0
                avg_tss = float(df["tss"].mean()) if "tss" in df.columns else 0.0
                total_duration = float(df["duration_minutes"].sum()) if "duration_minutes" in df.columns else 0.0
                
                return {
                    "period": period_name,
                    "activity_count": int(len(df)),
                    "total_tss": total_tss,
                    "avg_tss": avg_tss,
                    "total_duration": total_duration,
                    "activities_per_week": float(len(df) * 7 / period_length) if period_length > 0 else 0.0
                }
            
            recent_stats = get_period_stats(df1, f"последние {period1_days} дней", period1_days)
            previous_stats = get_period_stats(df2, f"предыдущие {period2_days} дней", period2_days)
            
            comparison: Dict[str, Any] = {}
            if not df1.empty and not df2.empty:
                comparison = {
                    "tss_change": float(recent_stats["total_tss"] - previous_stats["total_tss"]),
                    "activity_count_change": recent_stats["activity_count"] - previous_stats["activity_count"],
                    "volume_change": float(recent_stats["total_duration"] - previous_stats["total_duration"])
                }
            
            return {
                "period1_days": period1_days,
                "period2_days": period2_days,
                "recent_period": recent_stats,
                "previous_period": previous_stats,
                "comparison": comparison
            }
        
        except Exception as exc:
            fallback_summary: Dict[str, Any] = {"reason": str(exc)}
            
            try:
                fallback_summary["recent_activity_stats"] = self.get_activity_stats(period1_days)
            except Exception as stats_exc:  # pragma: no cover - очень редкие ошибки
                fallback_summary["recent_activity_stats_error"] = str(stats_exc)
            
            try:
                fallback_summary["training_load"] = self.analyze_training_load(days=period1_days)
            except Exception as load_exc:  # pragma: no cover
                fallback_summary["training_load_error"] = str(load_exc)
            fallback_summary["period1_days"] = period1_days
            fallback_summary["period2_days"] = period2_days
            
            return {
                "period1_days": period1_days,
                "period2_days": period2_days,
                "message": "Не удалось сравнить периоды из-за несогласованных дат. Возвращаю ручной обзор последних данных.",
                "fallback": fallback_summary
            }
    
    def get_activity_by_sport(self, sport: str, days: int = 30) -> Dict[str, Any]:
        """Получить активности по виду спорта"""
        df = self.db.get_activities(days)
        requested_sport = normalize_sport_key(sport)
        requested_label = sport_label(sport)
        
        if df.empty:
            return {"message": f"Нет активностей за {days} дней", "sport": requested_sport, "sport_label": requested_label}
        
        sport_df = (
            df[df["sport"].apply(normalize_sport_key) == requested_sport]
            if "sport" in df.columns
            else pd.DataFrame()
        )
        
        if sport_df.empty:
            available_sports = df["sport"].unique().tolist() if "sport" in df.columns else []
            return {
                "message": f"Нет активностей по виду спорта '{requested_label}'",
                "available_sports": sorted({sport_label(value) for value in available_sports}),
            }
        
        return {
            "sport": requested_sport,
            "sport_label": requested_label,
            "count": len(sport_df),
            "total_distance": float(sport_df["distance_km"].sum()) if "distance_km" in sport_df.columns else 0,
            "total_duration": float(sport_df["duration_minutes"].sum()),
            "avg_duration": float(sport_df["duration_minutes"].mean()),
            "total_tss": float(sport_df["tss"].sum()) if "tss" in sport_df.columns else 0,
            "avg_tss": float(sport_df["tss"].mean()) if "tss" in sport_df.columns else 0
        }
    
    def calculate_weekly_stats(self, weeks: int = 4) -> Dict[str, Any]:
        """Рассчитать недельную статистику"""
        days = weeks * 7
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": f"Нет данных за {weeks} недель"}
        
        # Группируем по неделям
        df["week"] = df["date"].dt.isocalendar().week
        weekly_stats = df.groupby("week").agg({
            "tss": "sum",
            "duration_minutes": "sum",
            "distance_km": "sum",
            "date": "count"  # количество тренировок
        }).round(2)
        
        weekly_data = []
        for week, stats in weekly_stats.iterrows():
            weekly_data.append({
                "week": int(week),
                "total_tss": float(stats["tss"]) if pd.notna(stats["tss"]) else 0,
                "training_sessions": int(stats["date"]),
                "total_duration_hours": float(stats["duration_minutes"] / 60),
                "total_distance": float(stats["distance_km"]) if pd.notna(stats["distance_km"]) else 0
            })
        
        return {
            "weeks_analyzed": weeks,
            "weekly_stats": weekly_data,
            "avg_weekly_tss": float(weekly_stats["tss"].mean()) if not weekly_stats["tss"].isna().all() else 0,
            "avg_sessions_per_week": float(weekly_stats["date"].mean())
        }
    
    def find_best_performances(self, metric: str = "tss", limit: int = 10) -> Dict[str, Any]:
        """Найти лучшие результаты по метрикам"""
        df = self.db.get_activities(90)  # За последние 3 месяца
        
        if df.empty:
            return {"message": "Нет данных для поиска лучших результатов"}
        
        available_metrics = ["tss", "duration_minutes", "distance_km", "avg_power", "avg_hr"]
        if metric not in available_metrics:
            return {
                "error": f"Метрика '{metric}' не доступна",
                "available_metrics": available_metrics
            }
        
        if metric not in df.columns or df[metric].isna().all():
            return {"message": f"Нет данных по метрике '{metric}'"}
        
        # Сортируем по убыванию и берем топ
        best_performances = df.nlargest(limit, metric)
        
        results = []
        for _, row in best_performances.iterrows():
            result = {
                "date": row["date"].strftime("%Y-%m-%d"),
                "sport": row.get("sport", "unknown"),
                "metric_value": float(row[metric]),
                "duration_minutes": float(row.get("duration_minutes", 0)),
                "description": f"{row.get('sport', 'unknown')} - {metric}: {row[metric]:.1f}"
            }
            results.append(result)
        
        return {
            "metric": metric,
            "best_performances": results,
            "analysis_period": "90 дней"
        }
    
    def analyze_recovery_state(self) -> Dict[str, Any]:
        """Проанализировать текущее состояние восстановления"""
        # HRV данные
        hrv_df = self.db.get_hrv_data(14)  # Последние 2 недели
        
        # Данные о нагрузке
        activities_df = self.db.get_activities(7)  # Последняя неделя
        
        recovery_analysis = {"factors": []}
        
        # Анализ HRV
        if not hrv_df.empty and len(hrv_df) >= 3:
            current_rmssd = hrv_df.iloc[0]["rmssd"]
            baseline_rmssd = hrv_df["rmssd"].median()
            
            recovery_analysis["hrv"] = {
                "current_rmssd": float(current_rmssd),
                "baseline_rmssd": float(baseline_rmssd),
                "deviation_percent": float((current_rmssd - baseline_rmssd) / baseline_rmssd * 100) if baseline_rmssd > 0 else 0
            }
            
            if current_rmssd > baseline_rmssd * 1.1:
                recovery_analysis["factors"].append("HRV значительно выше базового уровня - отличное восстановление")
            elif current_rmssd > baseline_rmssd * 0.95:
                recovery_analysis["factors"].append("HRV в норме - хорошее восстановление")
            else:
                recovery_analysis["factors"].append("HRV ниже базового уровня - возможна усталость")
        
        # Анализ нагрузки
        if not activities_df.empty:
            week_tss = activities_df["tss"].sum() if "tss" in activities_df.columns else 0
            recent_sessions = len(activities_df)
            
            recovery_analysis["training_load"] = {
                "week_tss": float(week_tss),
                "session_count": recent_sessions,
                "avg_tss_per_session": float(week_tss / recent_sessions) if recent_sessions > 0 else 0
            }
            
            if week_tss > 400:
                recovery_analysis["factors"].append("Высокая нагрузка за неделю - требуется внимание к восстановлению")
            elif recent_sessions > 6:
                recovery_analysis["factors"].append("Много тренировок за неделю - следите за признаками переутомления")
        
        # Общая рекомендация
        if not recovery_analysis["factors"]:
            recovery_analysis["factors"].append("Недостаточно данных для полноценного анализа восстановления")
        
        return recovery_analysis
    
    # === ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===
    
    def _interpret_tsb(self, tsb: float) -> str:
        """Интерпретация TSB (canonical TSB zone)"""
        return _TSB_TONE_TO_INTERPRETATION[tsb_zone(tsb)["tone"]]
    
    def _interpret_atl(self, atl: float) -> str:
        """Интерпретация ATL (уровень усталости)"""
        if atl > 80:
            return "высокая"
        elif atl > 50:
            return "умеренная"
        elif atl > 20:
            return "низкая"
        else:
            return "минимальная"
    
    def _calculate_fitness_trend(self, tss_data: List[float]) -> str:
        """Определение тренда фитнеса"""
        if len(tss_data) < 14:
            return "недостаточно данных"
        
        recent = np.mean(tss_data[-7:])
        previous = np.mean(tss_data[-14:-7])
        
        change = (recent - previous) / previous * 100 if previous > 0 else 0
        
        if change > 10:
            return "быстрый рост"
        elif change > 5:
            return "рост"
        elif change < -10:
            return "быстрое снижение"
        elif change < -5:
            return "снижение"
        else:
            return "стабильность"
    
    def _calculate_load_trend(self, df: pd.DataFrame) -> str:
        """Анализ тренда нагрузки"""
        if len(df) < 14:
            return "недостаточно данных"
        
        # Сравниваем последние 2 недели  
        df["date"] = pd.to_datetime(df["date"])
        now = pd.Timestamp.now()
        
        recent_week = df[df["date"] >= (now - timedelta(days=7))]
        previous_week = df[(df["date"] >= (now - timedelta(days=14))) & 
                          (df["date"] < (now - timedelta(days=7)))]
        
        recent_tss = recent_week["tss"].sum() if not recent_week.empty and "tss" in recent_week.columns else 0
        previous_tss = previous_week["tss"].sum() if not previous_week.empty and "tss" in previous_week.columns else 0
        
        if previous_tss == 0:
            return "нет данных для сравнения"
        
        change = (recent_tss - previous_tss) / previous_tss * 100
        
        if change > 20:
            return "резкое увеличение"
        elif change > 5:
            return "увеличение"
        elif change < -20:
            return "резкое снижение"
        elif change < -5:
            return "снижение"
        else:
            return "стабильность"
    
    def _analyze_intensity_distribution(self, df: pd.DataFrame) -> Dict[str, float]:
        """Анализ распределения интенсивности"""
        if df.empty or "tss" not in df.columns or df["tss"].isna().all():
            return {"low": 0, "moderate": 0, "high": 0}
        
        tss_values = df["tss"].dropna()
        total = len(tss_values)
        
        if total == 0:
            return {"low": 0, "moderate": 0, "high": 0}
        
        low = len(tss_values[tss_values < 50])
        moderate = len(tss_values[(tss_values >= 50) & (tss_values < 100)])
        high = len(tss_values[tss_values >= 100])
        
        return {
            "low_intensity_percent": round(low / total * 100, 1),
            "moderate_intensity_percent": round(moderate / total * 100, 1),
            "high_intensity_percent": round(high / total * 100, 1)
        }
    
    def _assess_recovery_state(self, recent_avg: float, baseline_avg: float) -> str:
        """Оценка состояния восстановления по HRV"""
        if recent_avg > baseline_avg * 1.1:
            return "отличное"
        elif recent_avg > baseline_avg * 0.95:
            return "хорошее"
        elif recent_avg > baseline_avg * 0.85:
            return "удовлетворительное"
        else:
            return "плохое"

    def propose_plan_build(
        self,
        goal_type: str = "Триатлон",
        distance: str = "Half",
        event_date: str = "",
        available_hours: float = 10.0,
        available_days: str = "",
    ) -> Dict[str, Any]:
        """Построить preview нового плана без сохранения в БД."""
        if not str(event_date or "").strip():
            return {
                "success": False,
                "error": "Укажи дату старта через event_date, например 2026-10-01.",
            }

        days_list = [day.strip() for day in str(available_days or "").split(",") if day.strip()] or None

        try:
            preview = planning_service.build_plan(
                self.db,
                goal_type=goal_type,
                distance=distance,
                event_date=str(event_date).strip(),
                available_hours=float(available_hours),
                available_days=days_list,
                persist=False,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        return {
            "is_proposal": True,
            "action": "build_plan",
            "params": {
                "goal_type": goal_type,
                "distance": distance,
                "event_date": str(event_date).strip(),
                "available_hours": float(available_hours),
                "available_days": days_list,
            },
            "preview": {
                "goal": preview.get("goal", {}),
                "total_weeks": len(preview.get("weeks", []) or []),
                "peak_tss": preview.get("totals", {}).get("peak_tss"),
                "total_tss": preview.get("totals", {}).get("total_tss"),
                "target_weekly_tss": preview.get("weekly_target", {}).get("target_weekly_tss"),
                "forecast_message": preview.get("forecast", {}).get("message"),
            },
        }

    def propose_plan_adjustment(self, weeks: int = 1) -> Dict[str, Any]:
        """Построить evidence-first future-only preview без сохранения."""
        try:
            resolved_weeks = int(weeks)
        except (TypeError, ValueError):
            return {"success": False, "error": "weeks должен быть целым числом."}

        try:
            result = planning_service.preview_weekly_rebalance(
                self.db,
                weeks=resolved_weeks,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if not result.get("has_plan"):
            return {"success": False, "error": "Нет активного плана для корректировки."}

        reconciliation = result.get("reconciliation", {}) or {}
        preview = result.get("preview", {}) or {}
        data_quality = reconciliation.get("data_quality", {}) or {}
        preview_payload = {
            "status": preview.get("status"),
            "reason": preview.get("reason"),
            "future_tss_delta": preview.get("future_tss_delta"),
            "changes": preview.get("changes", []),
            "coverage": data_quality.get("coverage"),
            "matched_count": data_quality.get("matched_count"),
            "planned_session_count": data_quality.get("planned_session_count"),
            "ambiguous_count": data_quality.get("ambiguous_count"),
        }
        params_payload = {
            "weeks": resolved_weeks,
            "as_of": preview.get("as_of"),
            "base_checkpoint_id": preview.get("base_checkpoint_id"),
            "preview_fingerprint": preview.get("preview_fingerprint"),
        }

        if preview.get("status") != "proposal":
            return {
                "is_proposal": False,
                "action": "adjust_plan",
                "status": "noop",
                "message": "Future-only корректировка не нужна или пока недостаточно надёжных фактов.",
                "params": {"weeks": resolved_weeks},
                "preview": preview_payload,
            }

        return {
            "is_proposal": True,
            "action": "adjust_plan",
            "params": params_payload,
            "preview": preview_payload,
        }

    def create_plan_constraint(
        self,
        date: str = "",
        kind: str = "unavailable",
        note: str = "",
    ) -> Dict[str, Any]:
        """Persist an explicit user/coach day constraint and apply it to the active plan."""
        try:
            resolved_date = _normalize_constraint_date(date)
            resolved_kind = _normalize_constraint_kind(kind)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        try:
            constraint = self.db.save_coach_constraint(
                date=resolved_date,
                kind=resolved_kind,
                source="coach",
                note=str(note or "").strip() or None,
                metadata={"created_by_tool": "create_plan_constraint"},
            )
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        checkpoint = self.db.get_latest_planning_checkpoint()
        goal_plan = restore_goal_plan_from_checkpoint(checkpoint)
        application = {"applied_count": 0, "protected_dates": [], "constraints": []}
        saved_checkpoint_id = None

        if goal_plan and goal_plan.get("daily_plan"):
            updated_plan, application = apply_constraints_to_goal_plan(goal_plan, [constraint])
            if int(application.get("applied_count") or 0) > 0:
                updated_plan["plan_revision"] = datetime.now().isoformat()
                updated_plan = with_checkpoint_provenance(
                    updated_plan,
                    source="coach_constraint",
                    parent_checkpoint_id=(checkpoint or {}).get("id"),
                )
                saved = self.db.save_planning_checkpoint(build_planning_checkpoint(updated_plan))
                saved_checkpoint_id = (saved or {}).get("id") or (saved or {}).get("checkpoint_id")

        return {
            "action": "create_plan_constraint",
            "constraint": constraint,
            "active_plan_present": bool(goal_plan and goal_plan.get("daily_plan")),
            "active_plan_updated": int(application.get("applied_count") or 0) > 0,
            "saved_checkpoint_id": saved_checkpoint_id,
            "constraint_application": application,
            "message": _constraint_tool_message(constraint, application),
        }

    def format_tool_descriptions_for_ai(self) -> str:
        """Форматирует описания инструментов для AI"""
        tools_desc = "ДОСТУПНЫЕ ИНСТРУМЕНТЫ:\n\n"
        
        for tool_name, description in self.get_available_tools().items():
            tools_desc += f"• **{tool_name}**: {description}\n"
        
        tools_desc += """\n
ИСПОЛЬЗОВАНИЕ ИНСТРУМЕНТОВ:
Чтобы получить конкретные данные, используй формат:
[TOOL: tool_name, param1=value1, param2=value2]

Примеры:
- [TOOL: get_recent_activities, limit=5] - последние 5 тренировок
- [TOOL: get_performance_metrics, days=30] - CTL/ATL/TSB на стабильном окне + тренд за 30 дней
- [TOOL: analyze_hrv_trends, days=14] - анализ HRV за 2 недели
- [TOOL: get_activity_by_sport, sport=cycling, days=30] - велотренировки
- [TOOL: get_training_status, days=30] - статус тренированности и readiness
- [TOOL: analyze_training_status, days=21] - выводы по readiness и нагрузке
- [TOOL: get_daily_health_stats, days=14] - показатели шагов и ЧСС покоя
- [TOOL: get_activities_by_date_range, start_date=2025-05-01, end_date=2025-05-31] - активности за май 2025
- [TOOL: get_active_plan] - активный тренировочный план (цель, старты с приоритетами, фазы, TSS-таргеты, текущая неделя current_week, недель до старта от сегодня)
- [TOOL: get_upcoming_workouts, days=7] - тренировки на ближайшие 7 дней из плана
- [TOOL: propose_plan_build, goal_type=Триатлон, distance=Half, event_date=2026-10-01, available_hours=10] - предложить новый план
- [TOOL: propose_plan_adjustment, weeks=1] - предложить корректировку активного плана
- [TOOL: create_plan_constraint, date=tomorrow, kind=sick, note=Температура] - отметить день как защищённый и убрать нагрузку из активного плана

ВАЖНО: Используй инструменты для получения точных, актуальных данных вместо общих предположений.
"""
        return tools_desc

    def get_activities_by_date_range(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получить активности за конкретный диапазон дат"""
        try:
            # Парсим даты
            from datetime import datetime
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            # Получаем все активности (берем большой период чтобы покрыть любые даты)
            df = self.db.get_activities(365 * 2)  # 2 года данных
            
            if df.empty:
                return {"message": "Нет данных активностей", "count": 0}
            
            # Преобразуем даты в datetime
            df["date"] = pd.to_datetime(df["date"])
            
            # Фильтруем по диапазону
            filtered_df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]
            
            if filtered_df.empty:
                return {
                    "message": f"Нет активностей в период с {start_date} по {end_date}",
                    "count": 0,
                    "period": f"{start_date} - {end_date}"
                }
            
            # Форматируем результат
            activities = []
            for _, row in filtered_df.iterrows():
                raw_sport = row.get("sport", "unknown")
                activity = {
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "date_label": format_date_label(row.get("date"), "weekday_short"),
                    "sport": normalize_sport_key(raw_sport),
                    "sport_label": sport_label(raw_sport),
                    "duration_minutes": float(row.get("duration_minutes", 0)),
                    "distance_km": float(row.get("distance_km", 0)) if pd.notna(row.get("distance_km")) else 0,
                    "tss": float(row.get("tss", 0)) if pd.notna(row.get("tss")) else 0,
                    "avg_hr": float(row.get("avg_hr", 0)) if pd.notna(row.get("avg_hr")) else 0
                }
                activities.append(activity)
            
            # Статистика за период
            stats = {
                "total_activities": len(filtered_df),
                "total_duration_hours": float(filtered_df["duration_minutes"].sum() / 60),
                "total_distance_km": float(filtered_df["distance_km"].sum()) if "distance_km" in filtered_df.columns else 0,
                "total_tss": float(filtered_df["tss"].sum()) if "tss" in filtered_df.columns else 0,
                "avg_tss_per_session": float(filtered_df["tss"].mean()) if "tss" in filtered_df.columns else 0,
                "sports_distribution": (
                    _localized_sports_distribution(filtered_df["sport"].value_counts().to_dict())
                    if "sport" in filtered_df.columns
                    else {}
                ),
                "period": f"{start_date} - {end_date}"
            }
            
            return {
                "count": len(activities),
                "period": f"{start_date} - {end_date}",
                "activities": activities,
                "statistics": stats
            }
            
        except ValueError as e:
            return {
                "error": f"Неверный формат даты. Используйте YYYY-MM-DD. Ошибка: {str(e)}",
                "example": "Пример: start_date=2025-05-01, end_date=2025-05-31"
            }
        except Exception as e:
            return {
                "error": f"Ошибка получения активностей по датам: {str(e)}"
            }
    
    def get_sleep_data(self, days: int = 30) -> Dict[str, Any]:
        """Получить данные сна за последние N дней"""
        try:
            sleep_df = self.db.get_sleep_data(days)
            
            if sleep_df.empty:
                return {
                    "has_data": False,
                    "message": f"Нет данных сна за последние {days} дней"
                }
            
            # Форматируем данные для AI
            sleep_records = []
            for _, row in sleep_df.head(10).iterrows():
                record = {
                    "date": row.get("date", ""),
                    "total_sleep_hours": round(row.get("total_sleep_minutes", 0) / 60, 1) if row.get("total_sleep_minutes") else None,
                    "sleep_score": row.get("sleep_score"),
                    "sleep_efficiency": row.get("sleep_efficiency"),
                    "deep_sleep_minutes": row.get("deep_sleep_minutes"),
                    "rem_sleep_minutes": row.get("rem_sleep_minutes"),
                    "light_sleep_minutes": row.get("light_sleep_minutes"),
                    "awakenings": row.get("awakenings_count")
                }
                sleep_records.append(record)
            
            return {
                "has_data": True,
                "period_days": days,
                "data_points": len(sleep_df),
                "recent_sleep": sleep_records
            }
            
        except Exception as e:
            return {
                "error": f"Ошибка получения данных сна: {str(e)}"
            }
    
    def get_sleep_stats(self, days: int = 30) -> Dict[str, Any]:
        """Получить статистику сна за период"""
        try:
            sleep_df = self.db.get_sleep_data(days)
            
            if sleep_df.empty:
                return {
                    "has_data": False,
                    "message": f"Нет данных сна за последние {days} дней"
                }
            
            # Рассчитываем статистику
            stats = {
                "period_days": days,
                "data_points": len(sleep_df),
                "avg_sleep_hours": sleep_df["total_sleep_minutes"].mean() / 60 if "total_sleep_minutes" in sleep_df.columns else None,
                "avg_sleep_score": sleep_df["sleep_score"].mean() if "sleep_score" in sleep_df.columns else None,
                "avg_sleep_efficiency": sleep_df["sleep_efficiency"].mean() if "sleep_efficiency" in sleep_df.columns else None,
                "avg_deep_sleep_minutes": sleep_df["deep_sleep_minutes"].mean() if "deep_sleep_minutes" in sleep_df.columns else None,
                "avg_rem_sleep_minutes": sleep_df["rem_sleep_minutes"].mean() if "rem_sleep_minutes" in sleep_df.columns else None,
                "avg_awakenings": sleep_df["awakenings_count"].mean() if "awakenings_count" in sleep_df.columns else None
            }
            
            # Анализ качества сна
            if "sleep_score" in sleep_df.columns and not sleep_df["sleep_score"].isna().all():
                current_score = sleep_df.iloc[0]["sleep_score"] if not sleep_df.empty else None
                if current_score:
                    if current_score >= 80:
                        sleep_quality = "отличное"
                    elif current_score >= 60:
                        sleep_quality = "хорошее"
                    elif current_score >= 40:
                        sleep_quality = "удовлетворительное"
                    else:
                        sleep_quality = "плохое"
                else:
                    sleep_quality = "неизвестно"
            else:
                sleep_quality = "неизвестно"
            
            stats["current_sleep_quality"] = sleep_quality
            
            return {
                "has_data": True,
                "statistics": stats
            }
            
        except Exception as e:
            return {
                "error": f"Ошибка расчета статистики сна: {str(e)}"
            }

    def get_training_status(self, days: int = 30) -> Dict[str, Any]:
        """Получить данные статуса тренированности Garmin"""
        df = self.db.get_training_status_history(days)
        
        if df.empty:
            return {
                "message": f"Нет данных статуса тренированности за последние {days} дней",
                "period_days": days
            }
        
        df["date"] = pd.to_datetime(df["date"])
        sorted_df = df.sort_values("date", ascending=False)
        latest = sorted_df.iloc[0].to_dict()
        latest_date = latest.get("date")
        if isinstance(latest_date, pd.Timestamp):
            latest["date"] = latest_date.strftime("%Y-%m-%d")
        latest_status = latest.get("training_status")
        latest["date_label"] = format_date_label(latest.get("date"))
        latest["training_status_key"] = normalize_training_status_key(latest_status)
        latest["training_status_label"] = training_status_label(latest_status)
        
        history_records: List[Dict[str, Any]] = []
        for _, row in sorted_df.head(10).iterrows():
            record = row.to_dict()
            record_date = record.get("date")
            if isinstance(record_date, pd.Timestamp):
                record["date"] = record_date.strftime("%Y-%m-%d")
            record["date_label"] = format_date_label(record.get("date"))
            record_status = record.get("training_status")
            record["training_status_key"] = normalize_training_status_key(record_status)
            record["training_status_label"] = training_status_label(record_status)
            history_records.append(record)
        
        summary = {
            "avg_training_readiness": df["training_readiness"].mean() if "training_readiness" in df.columns else None,
            "avg_training_load_7d": df["training_load_7d"].mean() if "training_load_7d" in df.columns else None,
            "avg_vo2_max": df["vo2_max"].mean() if "vo2_max" in df.columns else None,
            "status_distribution": (
                {
                    training_status_label(status): int(count)
                    for status, count in df["training_status"].dropna().value_counts().to_dict().items()
                }
                if "training_status" in df.columns
                else {}
            )
        }
        
        return {
            "has_data": True,
            "period_days": days,
            "latest": latest,
            "summary": summary,
            "history": history_records
        }

    def analyze_training_status(self, days: int = 30) -> Dict[str, Any]:
        """Проанализировать статус тренированности, readiness и нагрузку"""
        df = self.db.get_training_status_history(days)
        
        if df.empty:
            return {
                "message": f"Нет данных статуса тренированности за последние {days} дней"
            }
        
        df["date"] = pd.to_datetime(df["date"])
        sorted_df = df.sort_values("date", ascending=False)
        latest_row = sorted_df.iloc[0]
        
        insights: List[str] = []
        latest_status = latest_row.get("training_status")
        if latest_status:
            insights.append(f"Garmin фиксирует статус: {training_status_label(latest_status)}")
        
        readiness_info: Dict[str, Any] = {}
        if "training_readiness" in df.columns and not df["training_readiness"].isna().all():
            readiness_series = sorted_df["training_readiness"].dropna()
            current_readiness = readiness_series.iloc[0]
            avg_readiness = readiness_series.mean()
            readiness_info["current"] = f"Текущее readiness: {current_readiness:.0f}/100"
            readiness_info["average"] = f"Среднее за период: {avg_readiness:.1f}/100"
            
            if len(readiness_series) >= 5:
                recent_mean = readiness_series.head(3).mean()
                earlier_mean = readiness_series.iloc[3:6].mean() if len(readiness_series) >= 6 else readiness_series.tail(3).mean()
                if recent_mean > earlier_mean + 5:
                    readiness_info["trend"] = "Тренд: readiness улучшается"
                elif recent_mean < earlier_mean - 5:
                    readiness_info["trend"] = "Тренд: readiness снижается"
                else:
                    readiness_info["trend"] = "Тренд: без значимых изменений"
            
            if current_readiness < 40:
                insights.append("Низкий readiness — рекомендуется уделить внимание восстановлению")
            elif current_readiness > 70:
                insights.append("Высокий readiness — хорошее окно для интенсивных тренировок")
        
        load_info: Dict[str, Any] = {}
        if "training_load_7d" in df.columns and not df["training_load_7d"].isna().all():
            load_series = sorted_df["training_load_7d"].dropna()
            current_load = load_series.iloc[0]
            avg_load = load_series.mean()
            load_info["current"] = f"Нагрузка (7д): {current_load:.0f}"
            load_info["average"] = f"Среднее за период: {avg_load:.0f}"
            
            if len(load_series) >= 5:
                recent_mean = load_series.head(3).mean()
                earlier_mean = load_series.iloc[3:6].mean() if len(load_series) >= 6 else load_series.tail(3).mean()
                if recent_mean > earlier_mean * 1.2:
                    load_info["trend"] = "Тренд: нагрузка быстро растет"
                    insights.append("Нагрузка резко выросла — стоит контролировать усталость")
                elif recent_mean < earlier_mean * 0.8:
                    load_info["trend"] = "Тренд: нагрузка снижается"
                else:
                    load_info["trend"] = "Тренд: стабильная нагрузка"
            
            if current_load > avg_load * 1.3 and avg_load > 0:
                insights.append("Текущая нагрузка значительно выше средней")
            elif current_load < avg_load * 0.7:
                insights.append("Нагрузка ниже привычной — можно добавить объема")
        
        summary_text = training_status_label(latest_status)
        latest_date = latest_row.get("date")
        if isinstance(latest_date, pd.Timestamp):
            summary_text = f"{summary_text} от {format_date_label(latest_date)}"
        elif latest_date:
            summary_text = f"{summary_text} от {format_date_label(latest_date)}"
        
        return {
            "latest": {
                "summary": summary_text,
                "training_status_label": training_status_label(latest_status),
            },
            "insights": insights,
            "readiness_assessment": readiness_info,
            "load_assessment": load_info
        }

    def get_daily_health_stats(self, days: int = 30) -> Dict[str, Any]:
        """Получить статистику по ежедневным показателям здоровья"""
        df = self.db.get_daily_health(days)
        
        if df.empty:
            return {
                "message": f"Нет данных ежедневного здоровья за последние {days} дней",
                "period_days": days
            }
        
        df["date"] = pd.to_datetime(df["date"])

        # Сегодняшняя строка — незавершённый день: шаги/минуты ещё копятся,
        # поэтому агрегаты и тренд считаем только по завершённым дням (#126).
        today = pd.Timestamp(datetime.now().date())
        completed = df[df["date"] < today]
        has_today_partial = bool((df["date"] >= today).any())

        stats = {
            "avg_steps": completed["steps"].mean() if "steps" in completed.columns else None,
            "avg_resting_hr": completed["resting_hr"].mean() if "resting_hr" in completed.columns else None,
            "avg_active_minutes": completed["active_minutes"].mean() if "active_minutes" in completed.columns else None,
            "avg_calories_active": completed["calories_active"].mean() if "calories_active" in completed.columns else None,
            "total_steps": completed["steps"].sum() if "steps" in completed.columns else None
        }

        trend = None
        if "steps" in completed.columns:
            steps_series = completed.sort_values("date")["steps"].dropna()
            if len(steps_series) >= 2:
                slope = np.polyfit(range(len(steps_series)), steps_series, 1)[0]
                if slope > 0:
                    trend = "increasing"
                elif slope < 0:
                    trend = "decreasing"
                else:
                    trend = "stable"

        recent_entries = []
        for _, row in df.sort_values("date", ascending=False).head(5).iterrows():
            record = row.to_dict()
            record_date = record.get("date")
            if isinstance(record_date, pd.Timestamp):
                record["date"] = record_date.strftime("%Y-%m-%d")
            record["date_label"] = format_date_label(record.get("date"), "weekday_short")
            record["is_today_partial"] = is_today(record.get("date"))
            if record["is_today_partial"]:
                record["date_label"] = f"{record['date_label']} {TODAY_PARTIAL_NOTE_RU}"
            recent_entries.append(record)

        return {
            "period_days": days,
            "stats": stats,
            "aggregates_exclude_today": has_today_partial,
            "trend_steps": trend or "unknown",
            "trend_steps_label": trend_label(trend or "unknown"),
            "recent_entries": recent_entries
        }
    
    def get_active_plan(self) -> Dict[str, Any]:
        """Получить активный тренировочный план из последнего checkpoint."""
        goal_plan = restore_goal_plan_from_checkpoint(self.db.get_latest_planning_checkpoint())
        if not goal_plan:
            return {"has_plan": False, "message": "Активный план не найден. Пользователь ещё не построил план."}

        weekly_tss_plan = list(goal_plan.get("weekly_tss_plan") or [])
        events = normalized_events(goal_plan.get("events"))
        total_tss = int(sum(int(w or 0) for w in weekly_tss_plan))
        peak_tss = int(max(weekly_tss_plan)) if weekly_tss_plan else 0

        phases_raw = list(goal_plan.get("phases") or [])
        weekly_summary_raw = list(goal_plan.get("weekly_summary") or [])

        def _as_date(value: Any) -> Optional[date]:
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
            try:
                return date.fromisoformat(str(value)[:10])
            except (TypeError, ValueError):
                return None

        today = datetime.now().date()
        total_weeks = max(len(weekly_tss_plan), len(weekly_summary_raw))

        start_week = _as_date(goal_plan.get("start_week"))
        week_starts: List[Optional[date]] = []
        for i in range(total_weeks):
            ws = _as_date(weekly_summary_raw[i].get("week_start")) if i < len(weekly_summary_raw) else None
            if ws is None and start_week is not None:
                ws = start_week + timedelta(weeks=i)
            week_starts.append(ws)

        known_starts = [ws for ws in week_starts if ws is not None]
        plan_start = min(known_starts) if known_starts else None
        # Last planned day: end of the final plan week, or the last daily_plan session.
        plan_end: Optional[date] = max(known_starts) + timedelta(days=6) if known_starts else None
        if plan_end is None:
            daily_dates = [
                _as_date(item[0])
                for item in (goal_plan.get("daily_plan") or [])
                if isinstance(item, (list, tuple)) and item
            ]
            daily_dates = [d for d in daily_dates if d is not None]
            plan_end = max(daily_dates) if daily_dates else None

        # weeks_to_race is recomputed from today on every call: the checkpoint
        # stores the value from plan-build time, which goes stale immediately.
        event_date = _as_date(goal_plan.get("event_date"))
        race_or_end = event_date or (plan_end + timedelta(days=1) if plan_end else None)
        weeks_remaining = 0
        if race_or_end is not None and race_or_end > today:
            weeks_remaining = -((today - race_or_end).days // 7)  # ceil of days/7
        weeks_elapsed = max(0, (today - plan_start).days // 7) if plan_start else 0

        current_index: Optional[int] = None
        for i, ws in enumerate(week_starts):
            if ws is not None and ws <= today <= ws + timedelta(days=6):
                current_index = i
                break

        def _week_payload(i: int) -> Dict[str, Any]:
            row = weekly_summary_raw[i] if i < len(weekly_summary_raw) else {}
            ws = week_starts[i]
            tss = row.get("weekly_tss") if row else None
            if tss is None and i < len(weekly_tss_plan):
                tss = weekly_tss_plan[i]
            return {
                "week": i + 1,
                "week_start": ws.isoformat() if ws else "",
                "week_end": (ws + timedelta(days=6)).isoformat() if ws else "",
                "phase": str(row.get("phase") or (phases_raw[i] if i < len(phases_raw) else "")),
                "weekly_tss": int(float(tss or 0)),
                "is_current": i == current_index,
            }

        current_week = None
        if current_index is not None:
            current_week = {**_week_payload(current_index), "index": current_index + 1}
            current_week.pop("week", None)
            current_week.pop("is_current", None)

        if plan_start is not None and today < plan_start:
            plan_status = "not_started"
        elif plan_end is not None and today > plan_end:
            plan_status = "completed"
        else:
            plan_status = "active"

        # Compact preview (8 weeks max for readability), windowed so the
        # current week is always visible even in long plans.
        preview_start = 0
        if current_index is not None and current_index >= 8:
            preview_start = min(current_index - 3, max(0, total_weeks - 8))
        weeks_compact = [_week_payload(i) for i in range(preview_start, min(preview_start + 8, total_weeks))]

        return {
            "has_plan": True,
            "goal": {
                "goal_type": str(goal_plan.get("goal_type") or ""),
                "distance": str(goal_plan.get("distance") or ""),
                "event_date": event_date.isoformat() if event_date else "",
                "weeks_to_race": weeks_remaining,
            },
            "events": events,
            "timeline": {
                "today": today.isoformat(),
                "plan_start": plan_start.isoformat() if plan_start else "",
                "plan_end": plan_end.isoformat() if plan_end else "",
                "weeks_elapsed": weeks_elapsed,
                "weeks_remaining": weeks_remaining,
                "status": plan_status,
            },
            "current_week": current_week,
            "phases": list(dict.fromkeys(phases_raw)),
            "totals": {"total_tss": total_tss, "peak_tss": peak_tss, "total_weeks": len(weekly_tss_plan)},
            "weekly_tss_plan": [int(v or 0) for v in weekly_tss_plan],
            "weeks_preview": weeks_compact,
        }

    def get_upcoming_workouts(self, days: int = 7) -> Dict[str, Any]:
        """Получить ближайшие плановые тренировки из активного плана."""
        goal_plan = restore_goal_plan_from_checkpoint(self.db.get_latest_planning_checkpoint())
        if not goal_plan:
            return {"has_plan": False, "message": "Активный план не найден."}

        daily_plan = list(goal_plan.get("daily_plan") or [])
        templates = list(goal_plan.get("session_templates") or [])

        today = datetime.now().date()
        cutoff = today + timedelta(days=days)

        sessions = []
        for i, item in enumerate(daily_plan):
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            dt, total, parts = item
            session_date = dt.date() if hasattr(dt, "date") else dt
            if not (today <= session_date <= cutoff):
                continue
            total_tss = int(round(float(total or 0)))
            if total_tss <= 0:
                continue  # skip rest days
            tpl = templates[i] if i < len(templates) else {}
            phase = str((tpl or {}).get("phase") or "")
            # День может содержать несколько leaf-сессий (brick/составные).
            # Раскрываем их как отдельные тренировки, иначе Коуч видит день
            # как одну тренировку вместо двух (#266 browser acceptance).
            leaves = [dict(session or {}) for session in list((tpl or {}).get("sessions") or [])]
            if not leaves:
                leaves = [dict(tpl or {})]
            for leaf in leaves:
                leaf_tss = float(leaf.get("total_tss") or 0.0)
                if leaf_tss <= 0 and len(leaves) > 1:
                    continue  # нулевой leaf внутри составного дня — не тренировка
                sport = str(leaf.get("sport") or "")
                if not sport or sport == "—":
                    sport = (
                        max(dict(parts or {}).items(), key=lambda kv: float(kv[1] or 0), default=("bike", 0))[0]
                        if parts
                        else "bike"
                    )
                sessions.append({
                    "date": session_date.isoformat(),
                    "sport": sport,
                    "sport_label": str(leaf.get("sport_label") or sport),
                    "tss": int(round(leaf_tss)),
                    "name": str(
                        leaf.get("export_name")
                        or leaf.get("template_name")
                        or leaf.get("session_focus")
                        or "Сессия"
                    ),
                    "phase": phase,
                    "kind": str(leaf.get("kind") or "single"),
                })

        if not sessions:
            return {
                "has_plan": True,
                "message": f"Нет плановых тренировок в ближайшие {days} дней (возможно, уже выполнены или до них ещё далеко).",
                "days": days,
                "sessions": [],
            }

        return {"has_plan": True, "days": days, "sessions": sessions}

    def analyze_sleep_patterns(self, days: int = 30) -> Dict[str, Any]:
        """Анализ паттернов и качества сна"""
        try:
            sleep_df = self.db.get_sleep_data(days)
            
            if sleep_df.empty:
                return {
                    "has_data": False,
                    "message": f"Нет данных сна за последние {days} дней для анализа паттернов"
                }
            
            patterns = {}
            
            # Анализ продолжительности сна
            if "total_sleep_minutes" in sleep_df.columns:
                avg_sleep = sleep_df["total_sleep_minutes"].mean() / 60
                patterns["avg_sleep_duration"] = f"{avg_sleep:.1f} часов"
                
                # Соответствие рекомендациям (7-9 часов)
                optimal_sleep = sleep_df[(sleep_df["total_sleep_minutes"] >= 420) & 
                                       (sleep_df["total_sleep_minutes"] <= 540)]
                adherence = len(optimal_sleep) / len(sleep_df) * 100
                patterns["optimal_sleep_adherence"] = f"{adherence:.0f}% ночей в рекомендуемом диапазоне"
                
                # Постоянство сна
                sleep_std = sleep_df["total_sleep_minutes"].std() / 60
                if sleep_std < 0.5:
                    patterns["sleep_consistency"] = "очень постоянное"
                elif sleep_std < 1:
                    patterns["sleep_consistency"] = "постоянное"
                else:
                    patterns["sleep_consistency"] = "нерегулярное"
            
            # Анализ качества сна
            if "sleep_score" in sleep_df.columns and not sleep_df["sleep_score"].isna().all():
                avg_score = sleep_df["sleep_score"].mean()
                patterns["avg_sleep_score"] = f"{avg_score:.0f}/100"
                
                # Тренд сна за последние 7 дней
                if len(sleep_df) >= 7:
                    recent_score = sleep_df.head(7)["sleep_score"].mean()
                    older_score = sleep_df.tail(7)["sleep_score"].mean()
                    
                    if recent_score > older_score + 5:
                        patterns["sleep_trend"] = "улучшение"
                    elif recent_score < older_score - 5:
                        patterns["sleep_trend"] = "ухудшение"
                    else:
                        patterns["sleep_trend"] = "стабильность"
            
            # Анализ фаз сна
            if all(col in sleep_df.columns for col in ["deep_sleep_minutes", "rem_sleep_minutes", "light_sleep_minutes"]):
                total_phases = sleep_df["deep_sleep_minutes"] + sleep_df["rem_sleep_minutes"] + sleep_df["light_sleep_minutes"]
                patterns["deep_sleep_percentage"] = f"{(sleep_df['deep_sleep_minutes'] / total_phases * 100).mean():.1f}%"
                patterns["rem_sleep_percentage"] = f"{(sleep_df['rem_sleep_minutes'] / total_phases * 100).mean():.1f}%"
            
            # Рекомендации на основе паттернов
            recommendations = []
            
            if "avg_sleep_duration" in patterns:
                avg_hours = float(patterns["avg_sleep_duration"].split()[0])
                if avg_hours < 7:
                    recommendations.append("Увеличить продолжительность сна до 7-9 часов")
                elif avg_hours > 9:
                    recommendations.append("Рассмотреть оптимизацию времени сна")
            
            if "sleep_consistency" in patterns and patterns["sleep_consistency"] == "нерегулярное":
                recommendations.append("Установить регулярный режим сна")
            
            patterns["recommendations"] = recommendations
            
            return {
                "has_data": True,
                "period_days": days,
                "patterns": patterns
            }
            
        except Exception as e:
            return {
                "error": f"Ошибка анализа паттернов сна: {str(e)}"
            }


_CONSTRAINT_KIND_ALIASES = {
    "sick": "sick",
    "ill": "sick",
    "illness": "sick",
    "болею": "sick",
    "болезнь": "sick",
    "заболел": "sick",
    "заболела": "sick",
    "unavailable": "unavailable",
    "busy": "unavailable",
    "travel": "unavailable",
    "trip": "unavailable",
    "не могу": "unavailable",
    "недоступен": "unavailable",
    "недоступна": "unavailable",
    "перелет": "unavailable",
    "перелёт": "unavailable",
    "командировка": "unavailable",
    "forced_rest": "forced_rest",
    "rest": "forced_rest",
    "recovery": "forced_rest",
    "отдых": "forced_rest",
    "восстановление": "forced_rest",
    "manual_delete": "manual_delete",
    "delete": "manual_delete",
    "remove": "manual_delete",
    "удали": "manual_delete",
    "убери": "manual_delete",
    "удалить": "manual_delete",
    "disabled_plan_day": "disabled_plan_day",
    "disable": "disabled_plan_day",
    "off": "disabled_plan_day",
    "отключить": "disabled_plan_day",
}


def _normalize_constraint_kind(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        raise ValueError("kind is required")
    normalized = _CONSTRAINT_KIND_ALIASES.get(text)
    if normalized:
        return normalized
    allowed = sorted(set(_CONSTRAINT_KIND_ALIASES.values()))
    raise ValueError(
        f"Unsupported constraint kind '{value}'. Allowed kinds: {', '.join(allowed)}"
    )


def _normalize_constraint_date(value: Any) -> str:
    text = str(value or "").strip().lower()
    today = datetime.now().date()
    if text in {"today", "сегодня"}:
        return today.isoformat()
    if text in {"tomorrow", "завтра"}:
        return (today + timedelta(days=1)).isoformat()
    if not text:
        raise ValueError("date is required")
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD, today/tomorrow, сегодня/завтра") from exc


def _constraint_tool_message(
    constraint: Dict[str, Any],
    application: Dict[str, Any],
) -> str:
    date_text = constraint.get("date")
    kind = constraint.get("kind")
    if int(application.get("applied_count") or 0) > 0:
        return f"Ограничение {kind} на {date_text} сохранено и применено к активному плану."
    return f"Ограничение {kind} на {date_text} сохранено; активный план не изменён."

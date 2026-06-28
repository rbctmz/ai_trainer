"""Product-facing labels and formatting shared by API and coaching flows."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

WEEKDAY_LABELS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

SPORT_KEY_ALIASES = {
    "bike": "bike",
    "biking": "bike",
    "cycling": "bike",
    "ride": "bike",
    "virtual_ride": "bike",
    "run": "run",
    "running": "run",
    "trailrun": "run",
    "trail_running": "run",
    "jogging": "run",
    "swim": "swim",
    "swimming": "swim",
    "lap_swimming": "swim",
    "open_water_swimming": "swim",
    "pool_swimming": "swim",
    "walk": "walk",
    "walking": "walk",
    "hiking": "walk",
    "off": "off",
    "rest": "off",
    "recovery": "off",
    "strength": "strength",
    "strength_training": "strength",
    "yoga": "yoga",
    "вело": "bike",
    "велосипед": "bike",
    "бег": "run",
    "плавание": "swim",
    "ходьба": "walk",
    "отдых": "off",
    "сила": "strength",
    "йога": "yoga",
    "unknown": "other",
    "nan": "other",
}

SPORT_LABELS_RU = {
    "bike": "вело",
    "run": "бег",
    "swim": "плавание",
    "walk": "ходьба",
    "off": "отдых",
    "strength": "сила",
    "yoga": "йога",
    "other": "другое",
}

SPORT_EMOJIS = {
    "bike": "🚴",
    "run": "🏃",
    "swim": "🏊",
    "walk": "🚶",
    "off": "🛌",
    "strength": "💪",
    "yoga": "🧘",
    "other": "⚡",
}

TRAINING_STATUS_ALIASES = {
    "productive": "productive",
    "maintaining": "maintaining",
    "recovery": "recovery",
    "peaking": "peaking",
    "overreaching": "overreaching",
    "strained": "overreaching",
    "unproductive": "unproductive",
    "detraining": "detraining",
    "no_status": "no_status",
}

TRAINING_STATUS_LABELS_RU = {
    "productive": "Продуктивно",
    "maintaining": "Поддержание",
    "recovery": "Восстановление",
    "peaking": "Пиковая форма",
    "overreaching": "Перегрузка",
    "unproductive": "Непродуктивно",
    "detraining": "Снижение формы",
    "no_status": "Нет статуса",
}

TOOL_LABELS_RU = {
    "get_activities": "Активности",
    "get_hrv_data": "HRV",
    "get_activity_stats": "Сводка по тренировкам",
    "get_performance_metrics": "Форма и нагрузка",
    "get_recent_activities": "Последние тренировки",
    "analyze_training_load": "Нагрузка",
    "analyze_hrv_trends": "HRV-тренд",
    "compare_periods": "Сравнение периодов",
    "get_activity_by_sport": "Тренировки по виду спорта",
    "calculate_weekly_stats": "Недельная сводка",
    "find_best_performances": "Лучшие результаты",
    "analyze_recovery_state": "Восстановление",
    "get_activities_by_date_range": "Тренировки за период",
    "get_sleep_data": "Сон",
    "analyze_sleep_patterns": "Паттерны сна",
    "get_sleep_stats": "Сводка по сну",
    "get_training_status": "Статус Garmin",
    "analyze_training_status": "Статус тренированности",
    "get_daily_health_stats": "Ежедневное здоровье",
}

TREND_LABELS_RU = {
    "increasing": "рост",
    "decreasing": "снижение",
    "stable": "стабильно",
    "improving": "улучшается",
    "declining": "снижается",
    "unknown": "н/д",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def coerce_date(value: Any) -> date | None:
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


def format_date_label(value: Any, style: str = "full") -> str:
    resolved = coerce_date(value)
    if resolved is None:
        return str(value or "").strip()
    if style == "weekday_short":
        return f"{WEEKDAY_LABELS_RU[resolved.weekday()]} {resolved.strftime('%d.%m')}"
    if style == "short":
        return resolved.strftime("%d.%m")
    return resolved.strftime("%d.%m.%Y")


def normalize_sport_key(value: Any) -> str:
    normalized = _normalized_text(value)
    if not normalized or normalized in {"—", "-", "n/a", "none", "unknown", "nan"}:
        return "other"
    return SPORT_KEY_ALIASES.get(normalized, normalized)


def sport_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    key = normalize_sport_key(raw)
    if key == "other" and raw in {"—", "-"}:
        return "—"
    return SPORT_LABELS_RU.get(key, raw.replace("_", " "))


def sport_emoji(value: Any) -> str:
    return SPORT_EMOJIS.get(normalize_sport_key(value), SPORT_EMOJIS["other"])


def normalize_training_status_key(value: Any) -> str:
    normalized = _normalized_text(value)
    if not normalized:
        return "no_status"
    return TRAINING_STATUS_ALIASES.get(normalized, normalized)


def training_status_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Нет статуса"
    key = normalize_training_status_key(raw)
    return TRAINING_STATUS_LABELS_RU.get(key, raw)


def tool_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Инструмент"
    return TOOL_LABELS_RU.get(raw, raw.replace("_", " "))


def trend_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "н/д"
    return TREND_LABELS_RU.get(_normalized_text(raw), raw)

"""Intervals ordinal observations, independent of measured readiness scores."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

MAPPING_VERSION = "intervals_subjective_v1"
# All provider scales run from 1 (favorable) to 4 (unfavorable).
SCALES = {
    "sleepQuality": ("Качество сна", ("Отличное", "Хорошее", "Среднее", "Плохое")),
    "soreness": ("Болезненность", ("Низкая", "Средняя", "Высокая", "Крайняя")),
    "fatigue": ("Усталость перед тренировкой", ("Низкая", "Средняя", "Высокая", "Крайняя")),
    "stress": ("Субъективный стресс", ("Низкий", "Средний", "Высокий", "Крайний")),
    "mood": ("Настроение", ("Отличное", "Хорошее", "Нормальное", "Раздражённое")),
    "motivation": ("Мотивация", ("Очень высокая", "Высокая", "Средняя", "Низкая")),
    "injury": ("Травма — самооценка", ("Нет", "Дискомфорт", "Плохо", "Травма")),
    "hydration": ("Гидратация — самооценка", ("Отличная", "Нормальная", "Плохая", "Очень плохая")),
}


def utc_timestamp(value: Any) -> str | None:
    """Keep only offset-aware timestamps; unknown time is never inferred."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def normalize_subjective(row: Mapping[str, Any]) -> dict[str, Any]:
    """Replace a selected GET day snapshot; absent answers stay unavailable."""
    fields = {}
    for key in SCALES:
        value = row.get(key)
        valid = type(value) is int and 1 <= value <= 4
        fields[key] = {
            "state": "missing" if value is None else "present" if valid else "invalid",
            "value": value if valid else None,
        }
    return {
        "mapping_version": MAPPING_VERSION,
        "provider_updated_at": utc_timestamp(row.get("updated")),
        "fields": fields,
    }

"""Компактная нормализация интервалов Intervals.icu (#390).

Intervals.icu уже детектит интервалы (лапы/пары); здесь мы НЕ пересчитываем
их, а приводим ответ API к компактной структуре для карточки активности
(тот же паттерн, что с ``icu_training_load``: потребляем результат провайдера).

Fail-closed: неожиданная форма ответа поднимает ``ValueError``, а не теряет
данные молча — сервисный слой ловит ошибку и отдаёт кэш/``None``.
"""
from __future__ import annotations

from typing import Any, Mapping


_INTERVAL_FIELDS = (
    "start_index",
    "moving_time",
    "elapsed_time",
    "distance",
    "average_watts",
    "average_heartrate",
    "min_heartrate",
    "max_heartrate",
    "average_cadence",
    "zone",
    "training_load",
    "average_speed",
)


def _compact_number(value: Any) -> int | float | None:
    """Round a scalar to at most 1 decimal; ints stay ints; junk -> None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return round(number, 1)


def _compact_interval(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("Intervals.icu interval entries must be objects")
    return {field: _compact_number(raw.get(field)) for field in _INTERVAL_FIELDS}


def normalize_intervals_payload(payload: Any) -> dict[str, Any]:
    """Compact ``IntervalsDTO`` (``?intervals=true``) into card-friendly shape.

    Returns ``{"analyzed": str|None, "intervals": [...], "groups": [...]}``.
    Raises ``ValueError`` on a malformed payload (fail-closed).
    """
    if not isinstance(payload, Mapping):
        raise ValueError("Intervals.icu intervals payload must be an object")

    raw_intervals = payload.get("icu_intervals")
    if raw_intervals is None:
        raw_intervals = []
    if not isinstance(raw_intervals, list):
        raise ValueError("Intervals.icu `icu_intervals` must be a list")

    raw_groups = payload.get("icu_groups")
    if raw_groups is None:
        raw_groups = []
    if not isinstance(raw_groups, list):
        raise ValueError("Intervals.icu `icu_groups` must be a list")

    analyzed = payload.get("analyzed")
    return {
        "analyzed": str(analyzed).strip() if analyzed not in (None, "") else None,
        "intervals": [_compact_interval(row) for row in raw_intervals],
        "groups": [_compact_interval(row) for row in raw_groups],
    }


__all__ = ["normalize_intervals_payload"]

"""Компактная нормализация структуры фактической активности.

Intervals.icu уже определяет интервалы, а Garmin отдаёт записанные устройством
круги. Здесь мы не пересчитываем структуру, а приводим оба ответа к одному
компактному контракту карточки активности.

Fail-closed: неожиданная форма ответа поднимает ``ValueError``, а не теряет
данные молча — сервисный слой ловит ошибку и отдаёт кэш/``None``.
"""
from __future__ import annotations

from typing import Any, Mapping


_INTERVAL_FIELDS = (
    "start_index",
    "moving_time",
    "elapsed_time",
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


def _distance_to_km(value: Any) -> float | None:
    """Intervals.icu interval ``distance`` is in metres -> compact ``distance_km``."""
    if value is None or isinstance(value, bool):
        return None
    try:
        metres = float(value)
    except (TypeError, ValueError):
        return None
    if metres < 0:
        return None
    return round(metres / 1000.0, 2)


def _compact_interval(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("Intervals.icu interval entries must be objects")
    compact = {field: _compact_number(raw.get(field)) for field in _INTERVAL_FIELDS}
    compact["distance_km"] = _distance_to_km(raw.get("distance"))
    return compact


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
    # #462: провайдер сам считает соответствие спаренной активности доставленному
    # воркауту; без спаривания он отдаёт compliance=0.0 — это не оценка, а заглушка.
    paired_event_id = _compact_number(payload.get("paired_event_id"))
    compliance = (
        _compact_number(payload.get("compliance")) if paired_event_id is not None else None
    )
    return {
        "source": "intervals",
        "analyzed": str(analyzed).strip() if analyzed not in (None, "") else None,
        "intervals": [_compact_interval(row) for row in raw_intervals],
        "groups": [_compact_interval(row) for row in raw_groups],
        "paired_event_id": paired_event_id,
        "compliance": compliance,
    }


def _first_number(raw: Mapping[str, Any], *fields: str) -> int | float | None:
    for field in fields:
        value = _compact_number(raw.get(field))
        if value is not None:
            return value
    return None


def _garmin_interval(raw: Any, start_index: int | float) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("Garmin lap entries must be objects")

    moving_time = _first_number(raw, "movingDuration", "duration")
    elapsed_time = _first_number(raw, "elapsedDuration", "duration")
    intensity = raw.get("intensityType")
    intensity_type = (
        str(intensity).strip().lower() if intensity not in (None, "") else None
    )
    return {
        "start_index": _compact_number(start_index),
        "moving_time": moving_time,
        "elapsed_time": elapsed_time,
        "average_watts": _first_number(raw, "averagePower"),
        "average_heartrate": _first_number(raw, "averageHR"),
        "min_heartrate": _first_number(raw, "minHR"),
        "max_heartrate": _first_number(raw, "maxHR"),
        "average_cadence": _first_number(
            raw, "averageRunCadence", "averageBikeCadence", "averageCadence"
        ),
        "zone": _first_number(raw, "zone"),
        "training_load": _first_number(raw, "trainingLoad"),
        "average_speed": _first_number(raw, "averageSpeed", "averageMovingSpeed"),
        "distance_km": _distance_to_km(raw.get("distance")),
        "intensity_type": intensity_type,
    }


def normalize_garmin_splits_payload(payload: Any) -> dict[str, Any]:
    """Привести Garmin ``lapDTOs`` к общему контракту структуры карточки.

    ``start_index`` — накопленное прошедшее время предыдущих кругов в секундах.
    Так паузы между движущимися отрезками остаются видимыми на полосе факта.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("Garmin splits payload must be an object")

    raw_laps = payload.get("lapDTOs")
    if raw_laps is None:
        raw_laps = []
    if not isinstance(raw_laps, list):
        raise ValueError("Garmin `lapDTOs` must be a list")

    intervals: list[dict[str, Any]] = []
    cursor: int | float = 0
    for raw in raw_laps:
        compact = _garmin_interval(raw, cursor)
        intervals.append(compact)
        elapsed = compact.get("elapsed_time")
        moving = compact.get("moving_time")
        cursor = round(float(cursor) + float(elapsed or moving or 0), 1)

    return {
        "source": "garmin",
        "analyzed": None,
        "intervals": intervals,
        "groups": [],
    }


__all__ = ["normalize_garmin_splits_payload", "normalize_intervals_payload"]

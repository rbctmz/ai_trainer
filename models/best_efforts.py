"""Компактная нормализация best-efforts Intervals.icu (#382).

Intervals.icu уже считает лучшие усилия (best efforts); здесь мы НЕ пересчитываем
их, а приводим ответ API к компактной структуре для карточки активности
(тот же паттерн, что с интервалами в #390: потребляем результат провайдера).

Fail-closed: неожиданная форма ответа поднимает ``ValueError``, а не теряет
данные молча — сервисный слой ловит ошибку и отдаёт кэш/``None``.
"""
from __future__ import annotations

from typing import Any, Mapping


_EFFORT_FIELDS = ("start_index", "end_index", "average", "duration")


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


def _compact_effort(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("Intervals.icu best-effort entries must be objects")
    compact = {field: _compact_number(raw.get(field)) for field in _EFFORT_FIELDS}
    compact["distance_km"] = _distance_to_km(raw.get("distance"))
    return compact


def _distance_to_km(value: Any) -> float | None:
    """Intervals.icu effort ``distance`` is in metres -> compact ``distance_km``."""
    if value is None or isinstance(value, bool):
        return None
    try:
        metres = float(value)
    except (TypeError, ValueError):
        return None
    if metres < 0:
        return None
    return round(metres / 1000.0, 2)


def normalize_best_efforts_payload(
    payload: Any, *, stream: str = "watts", duration: int = 60
) -> dict[str, Any]:
    """Compact ``{efforts: [...]}`` into a card-friendly shape.

    Returns ``{"stream": str, "duration": int, "efforts": [...]}`` where each
    effort is ``{start_index, end_index, average, duration, distance_km}``.
    Raises ``ValueError`` on a malformed payload (fail-closed).
    """
    if not isinstance(payload, Mapping):
        raise ValueError("Intervals.icu best-efforts payload must be an object")

    raw_efforts = payload.get("efforts")
    if raw_efforts is None:
        raw_efforts = []
    if not isinstance(raw_efforts, list):
        raise ValueError("Intervals.icu `efforts` must be a list")

    return {
        "stream": str(stream or "watts"),
        "duration": int(duration),
        "efforts": [_compact_effort(row) for row in raw_efforts],
    }


__all__ = ["normalize_best_efforts_payload"]

"""Компактная нормализация power curve Intervals.icu (#382).

Intervals.icu уже считает power curve (пиковая мощность на каждой длительности);
здесь мы НЕ пересчитываем её, а приводим ответ API к компактной структуре для
карточки активности (тот же паттерн, что с интервалами в #390).

Fail-closed: неожиданная форма ответа поднимает ``ValueError``, а не теряет
данные молча — сервисный слой ловит ошибку и отдаёт кэш/``None``.
"""
from __future__ import annotations

from typing import Any, Mapping


# Standard card-friendly durations (seconds) surfaced as headline peaks.
_HEADLINE_DURATIONS = (5, 60, 300, 1200, 3600)
_HEADLINE_LABELS = {
    5: "5s",
    60: "1min",
    300: "5min",
    1200: "20min",
    3600: "60min",
}


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


def _round_power(value: Any) -> int | None:
    """Power (watts) rounded to the nearest integer; junk -> None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _value_at(secs: list[Any], values: list[Any], target: int) -> Any | None:
    """Closest raw value at/around ``target`` seconds (linear-nearest).

    Returns the raw provider value (caller rounds to the right precision).
    """
    if not secs or not values or len(secs) != len(values):
        return None
    try:
        int_targets = [int(round(float(s))) for s in secs]
    except (TypeError, ValueError):
        return None
    # Exact match first (Intervals.icu uses common durations incl. 5/60/300/1200).
    if target in int_targets:
        return values[int_targets.index(target)]
    # Nearest duration within a small tolerance.
    deltas = [(abs(it - target), i) for i, it in enumerate(int_targets)]
    delta, idx = min(deltas, key=lambda x: x[0])
    if delta > max(5, target * 0.05):  # >5s or 5% off — too far
        return None
    return values[idx]


def normalize_power_curve_payload(payload: Any) -> dict[str, Any]:
    """Compact a PowerCurve list ``[{secs, values, watts_per_kg, ...}]`` into shape.

    The provider returns a single-element list; we take the first curve. Returns::

        {
          "weight": float|None,
          "peaks": [{"label": "5s", "duration": 5, "watts": int|None,
                     "watts_per_kg": float|None}, ...],
          "vo2max_5m": float|None,
          "compound_score_5m": float|None,
        }

    An empty list (activity without power) -> ``{"peaks": [], ...}`` (no data,
    not an error). Raises ``ValueError`` on a malformed payload (fail-closed).
    """
    if not isinstance(payload, list):
        raise ValueError("Intervals.icu power-curves payload must be a list")
    if not payload:
        return {"weight": None, "peaks": [], "vo2max_5m": None, "compound_score_5m": None}

    curve = payload[0]
    if not isinstance(curve, Mapping):
        raise ValueError("Intervals.icu power-curve entry must be an object")

    secs_raw = curve.get("secs")
    values_raw = curve.get("values")
    wkg_raw = curve.get("watts_per_kg")
    secs = list(secs_raw) if isinstance(secs_raw, list) else []
    values = list(values_raw) if isinstance(values_raw, list) else []
    wkg = list(wkg_raw) if isinstance(wkg_raw, list) else []

    peaks = []
    for duration in _HEADLINE_DURATIONS:
        watts_raw = _value_at(secs, values, duration)
        wkg_raw = _value_at(secs, wkg, duration)
        peaks.append(
            {
                "label": _HEADLINE_LABELS[duration],
                "duration": duration,
                "watts": _round_power(watts_raw),
                "watts_per_kg": _compact_number(wkg_raw),
            }
        )

    return {
        "weight": _compact_number(curve.get("weight")),
        "peaks": peaks,
        "vo2max_5m": _compact_number(curve.get("vo2max_5m")),
        "compound_score_5m": _compact_number(curve.get("compound_score_5m")),
    }


__all__ = ["normalize_power_curve_payload"]

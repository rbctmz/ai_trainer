"""Общий источник формул кандидатов вело-TSS по ЧСС (#444 S3).

Работает над теневыми парами из bike_hr_quality_pairs (словари с полями
таблицы) — единая математика для dev-отчёта и гейта перестановки зон/avgHR.
Продуктовый каскад (data/data_processor.py) НЕ меняется; M0-скрипт
research/issue444_m0_bike_hr_tss.py остаётся замороженным evidence.
"""
from __future__ import annotations

import math
from typing import Optional


BIKE_HR_ZONE_TSS_WEIGHTS = (0.2, 0.35, 0.65, 0.95, 1.3)
_ZONE_MINUTES = (
    "hr_zone_minutes_z1",
    "hr_zone_minutes_z2",
    "hr_zone_minutes_z3",
    "hr_zone_minutes_z4",
    "hr_zone_minutes_z5",
)


def _f(value) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _hours(pair: dict) -> Optional[float]:
    moving = _f(pair.get("moving_minutes"))
    if not moving or moving <= 0:
        return None
    return moving / 60.0


def zones_tss(pair: dict) -> Optional[float]:
    """Кандидат «фиксированные веса HR-зон»: Σ minutes_z × weight_z."""
    minutes = [_f(pair.get(column)) for column in _ZONE_MINUTES]
    if any(value is None for value in minutes):
        return None
    total = sum(
        (value or 0.0) * weight
        for value, weight in zip(minutes, BIKE_HR_ZONE_TSS_WEIGHTS)
    )
    return float(total) if total > 0 else None


def avg_hr_tss(pair: dict) -> Optional[float]:
    """Кандидат «средняя ЧСС»: hours × (avg_hr / LTHR)² × 100."""
    hours = _hours(pair)
    avg_hr = _f(pair.get("avg_hr"))
    lthr = _f(pair.get("lthr"))
    if not hours or not avg_hr or avg_hr <= 0 or not lthr or lthr <= 0:
        return None
    return float(hours * (avg_hr / lthr) ** 2 * 100.0)


def hrss_tss(pair: dict) -> Optional[float]:
    """Кандидат «HRSS (Karvonen)»: hours × ((avg_hr − RHR)/(LTHR − RHR))² × 100."""
    hours = _hours(pair)
    avg_hr = _f(pair.get("avg_hr"))
    rhr = _f(pair.get("rhr"))
    lthr = _f(pair.get("lthr"))
    if not hours or not avg_hr or avg_hr <= 0 or not lthr or lthr <= 0:
        return None
    if not rhr or rhr <= 0 or (lthr - rhr) <= 0 or avg_hr <= rhr:
        return None
    intensity = (avg_hr - rhr) / (lthr - rhr)
    return float(hours * intensity ** 2 * 100.0)


def power_tss_target(pair: dict) -> Optional[float]:
    """Целевой Power TSS: hours × (power / FTP_на_дату)² × 100, NP → avg_power."""
    hours = _hours(pair)
    power = _f(pair.get("normalized_power")) or _f(pair.get("avg_power"))
    ftp = _f(pair.get("ftp_on_date"))
    if not hours or not power or power <= 0 or not ftp or ftp <= 0:
        return None
    return float(hours * (power / ftp) ** 2 * 100.0)

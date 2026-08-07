"""Fetch-and-cache power curve Intervals.icu для карточки активности (#382).

Карточка открывается офлайн: power curve — обогащение, не блокер. Сервис
резолвит Intervals-id через provider-links, при настроенном провайдере тянет
``/power-curves``, нормализует к headline-пикам (5s/1min/5min/20min/60min) и
кэширует компактную структуру; при сбое сети/провайдера отдаёт кэш, иначе
``None``. Гибридный фолбэк на локальный mean-max из стримов — Milestone 4.
"""
from __future__ import annotations

from typing import Any

from models.power_curve import normalize_power_curve_payload
from services import intervals_icu
from services.intervals_icu import IntervalsICUClient, IntervalsICUError


def fetch_activity_power_curve(
    database: Any,
    activity_id: str,
    client: IntervalsICUClient | None = None,
) -> dict[str, Any] | None:
    """Return the compact power curve for a card, fetching on demand with a cache.

    - No Intervals provider link -> ``None`` (activity is not Intervals-backed;
      the local mean-max fallback for Garmin-only activities is Milestone 4).
    - Provider not configured -> cached curve if any, else ``None``.
    - Provider fetch fails or payload is malformed -> cached curve if any,
      else ``None`` (fail-open at the display boundary, never raises).
    - Activity without power (swim/run) -> ``{"peaks": [], ...}`` cached as
      "no curve", not ``None`` — so the card can distinguish "checked, none"
      from "never checked". ``None`` is reserved for "no Intervals link".
    """
    intervals_id = database.get_intervals_provider_activity_id(activity_id)
    if not intervals_id:
        return None

    client = client or intervals_icu.get_client()
    if not client.is_configured():
        return database.get_activity_power_curve(activity_id)

    try:
        payload = client.get_activity_power_curve(intervals_id)
        compact = normalize_power_curve_payload(payload)
    except (IntervalsICUError, ValueError):
        return database.get_activity_power_curve(activity_id)

    database.save_activity_power_curve(activity_id, compact)
    return compact


__all__ = ["fetch_activity_power_curve"]

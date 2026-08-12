"""Fetch-and-cache power curve Intervals.icu для карточки активности (#382).

Карточка открывается офлайн: power curve — обогащение, не блокер. Сервис
резолвит Intervals-id через provider-links, при настроенном провайдере тянет
``/power-curves``, нормализует к headline-пикам (5s/1min/5min/20min/60min) и
кэширует компактную структуру; при сбое сети/провайдера отдаёт кэш, иначе
``None``. Гибридный фолбэк на локальный mean-max из стримов — Milestone 4.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from models.power_curve import normalize_power_curve_payload
from services import intervals_icu
from services.intervals_icu import IntervalsICUClient, IntervalsICUError


_SIXTY_MINUTES_SECONDS = 3600


def _enrich_sixty_minute_peak(
    compact: dict[str, Any],
    efforts: list[Mapping[str, Any]],
) -> None:
    """Fill the provider curve's missing 60-minute headline in place."""
    peak = next(
        (
            item
            for item in compact.get("peaks", [])
            if item.get("duration") == _SIXTY_MINUTES_SECONDS
            and item.get("watts") is None
        ),
        None,
    )
    if peak is None or not efforts:
        return

    average = efforts[0].get("average")
    if average is None or isinstance(average, bool):
        return
    try:
        watts = float(average)
    except (TypeError, ValueError):
        return
    if not math.isfinite(watts) or watts <= 0:
        return

    peak["watts"] = int(round(watts))
    weight = compact.get("weight")
    if (
        isinstance(weight, (int, float))
        and not isinstance(weight, bool)
        and math.isfinite(weight)
        and weight > 0
    ):
        peak["watts_per_kg"] = round(watts / weight, 1)


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

    sixty_minute_peak_missing = any(
        peak.get("duration") == _SIXTY_MINUTES_SECONDS
        and peak.get("watts") is None
        for peak in compact.get("peaks", [])
    )
    if sixty_minute_peak_missing:
        try:
            efforts = client.get_activity_best_efforts(
                intervals_id,
                stream="watts",
                duration=_SIXTY_MINUTES_SECONDS,
                count=1,
            )
        except (IntervalsICUError, ValueError):
            # The headline enrichment is optional. A transient failure here
            # must not hide the freshly fetched 5s..20min curve behind a stale
            # cache (or None for a first view); persist the honest partial
            # result and let a later card read retry the 60-minute peak.
            database.save_activity_power_curve(activity_id, compact)
            return compact
        _enrich_sixty_minute_peak(compact, efforts)

    database.save_activity_power_curve(activity_id, compact)
    return compact


__all__ = ["fetch_activity_power_curve"]

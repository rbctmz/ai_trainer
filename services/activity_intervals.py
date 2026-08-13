"""Чтение и обогащение структуры фактической активности для карточки.

Карточка открывается офлайн: Garmin-круги сохраняются при синхронизации, а
Intervals.icu добавляет отдельно определённые интервалы. При сбое сети сервис
отдаёт локальный кэш, иначе ``None``.
"""
from __future__ import annotations

from typing import Any

from models.activity_intervals import normalize_intervals_payload
from services import intervals_icu
from services.intervals_icu import IntervalsICUClient, IntervalsICUError


def fetch_activity_intervals(
    database: Any,
    activity_id: str,
    client: IntervalsICUClient | None = None,
) -> dict[str, Any] | None:
    """Return compact intervals for a card, fetching on demand with a cache.

    - No Intervals provider link -> cached Garmin laps, if available.
    - Provider not configured -> cached intervals if any, else ``None``.
    - Provider fetch fails or payload is malformed -> cached intervals if any,
      else ``None`` (fail-open at the display boundary, never raises).
    """
    cached = database.get_activity_intervals(activity_id)
    intervals_id = database.get_intervals_provider_activity_id(activity_id)
    if not intervals_id:
        return cached

    client = client or intervals_icu.get_client()
    if not client.is_configured():
        return cached

    try:
        payload = client.get_activity_intervals(intervals_id)
        compact = normalize_intervals_payload(payload)
    except (IntervalsICUError, ValueError):
        return cached

    if cached and not compact["intervals"] and not compact["groups"]:
        return cached

    garmin_laps = None
    if cached:
        if cached.get("source") == "garmin":
            garmin_laps = cached.get("intervals")
        else:
            garmin_laps = cached.get("garmin_laps")
    if garmin_laps:
        compact["garmin_laps"] = garmin_laps

    database.save_activity_intervals(activity_id, compact)
    return compact


__all__ = ["fetch_activity_intervals"]

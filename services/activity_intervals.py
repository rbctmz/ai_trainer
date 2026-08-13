"""Чтение и обогащение структуры фактической активности для карточки.

Карточка открывается офлайн: Garmin-круги сохраняются при синхронизации, а
Intervals.icu может обогатить их уже определёнными интервалами. При сбое сети
сервис отдаёт локальный кэш, иначе ``None``.
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

    if (
        cached
        and cached.get("source") == "garmin"
        and not compact["intervals"]
        and not compact["groups"]
    ):
        return cached

    database.save_activity_intervals(activity_id, compact)
    return compact


__all__ = ["fetch_activity_intervals"]

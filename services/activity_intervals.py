"""Fetch-and-cache интервалов Intervals.icu для карточки активности (#390).

Карточка открывается офлайн: интервалы — обогащение, не блокер. Сервис
резолвит Intervals-id через provider-links, при настроенном провайдере
тянет ``?intervals=true``, нормализует и кэширует компактную структуру;
при сбое сети/провайдера отдаёт кэш, иначе ``None``.
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

    - No Intervals provider link -> ``None`` (activity is not Intervals-backed).
    - Provider not configured -> cached intervals if any, else ``None``.
    - Provider fetch fails or payload is malformed -> cached intervals if any,
      else ``None`` (fail-open at the display boundary, never raises).
    """
    intervals_id = database.get_intervals_provider_activity_id(activity_id)
    if not intervals_id:
        return None

    client = client or intervals_icu.get_client()
    if not client.is_configured():
        return database.get_activity_intervals(activity_id)

    try:
        payload = client.get_activity_intervals(intervals_id)
        compact = normalize_intervals_payload(payload)
    except (IntervalsICUError, ValueError):
        return database.get_activity_intervals(activity_id)

    database.save_activity_intervals(activity_id, compact)
    return compact


__all__ = ["fetch_activity_intervals"]

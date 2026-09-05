"""Чтение и обогащение структуры фактической активности для карточки.

Карточка открывается офлайн: Garmin-круги сохраняются при синхронизации, а
Intervals.icu добавляет отдельно определённые интервалы. При сбое сети сервис
отдаёт локальный кэш, иначе ``None``.
"""
from __future__ import annotations

from typing import Any, Sequence

from models.activity_intervals import normalize_intervals_payload
from models.plan_vs_fact import structure_from_streams
from services import intervals_icu
from services.intervals_icu import IntervalsICUClient, IntervalsICUError


_STREAM_TYPES = "time,watts,heartrate,distance"


def _is_provider_cache(
    cached: dict[str, Any] | None,
    intervals_id: str | None,
) -> bool:
    if not cached:
        return False
    source = cached.get("source")
    if source == "intervals":
        return True
    if source is not None or not intervals_id:
        return False
    # Pre-#435 provider caches have no source marker. Require the normalized
    # compact shape plus an Intervals provider link so a malformed mapping or a
    # Garmin-only legacy row cannot suppress the first provider enrichment.
    return isinstance(cached.get("intervals"), list) and isinstance(
        cached.get("groups"), list
    )


def fetch_activity_intervals(
    database: Any,
    activity_id: str,
    client: IntervalsICUClient | None = None,
    *,
    refresh: bool = False,
) -> dict[str, Any] | None:
    """Return compact intervals for a card, fetching on demand with a cache.

    - No Intervals provider link -> cached Garmin laps, if available.
    - Provider not configured -> cached intervals if any, else ``None``.
    - Provider fetch fails or payload is malformed -> cached intervals if any,
      else ``None`` (fail-open at the display boundary, never raises).
    """
    cached = database.get_activity_intervals(activity_id)
    intervals_id = database.get_intervals_provider_activity_id(activity_id)
    # A normalized provider projection is complete card enrichment, including
    # an honest empty intervals list. Serve it locally; callers that own an
    # explicit refresh lifecycle may opt in without making every card open wait
    # for Intervals.icu.
    if not refresh and _is_provider_cache(cached, intervals_id):
        return cached
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


def fetch_stream_structure(
    database: Any,
    activity_id: str,
    planned: Sequence[Any],
    client: IntervalsICUClient | None = None,
) -> list:
    """Структура факта из 1 Гц-стримов спаренной активности (#462).

    Гейт — ``paired_event_id`` в записи интервалов: режем по плановым шагам
    только активности, спаренные с доставленным воркаутом (то же условие, при
    котором провайдер показывает свой compliance). Любой сбой — ``[]``
    (fail-open к прежнему пути), полные стримы не персистим (#390).
    """
    cached = database.get_activity_intervals(activity_id)
    if not isinstance(cached, dict) or cached.get("paired_event_id") is None:
        return []
    if not planned:
        return []
    client = client or intervals_icu.get_client()
    if not client.is_configured():
        return []
    intervals_id = database.get_intervals_provider_activity_id(activity_id)
    if not intervals_id:
        return []
    try:
        streams = client.get_activity_streams(intervals_id, types=_STREAM_TYPES)
        return structure_from_streams(planned, streams)
    except (IntervalsICUError, ValueError):
        return []


__all__ = ["fetch_activity_intervals", "fetch_stream_structure"]

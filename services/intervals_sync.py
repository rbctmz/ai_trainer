"""Intervals.icu activity adapter (M1 #270, §11 step 3 / slice-spec §3).

``sync_intervals_data`` is the Intervals-only vertical — symmetric to
``sync_garmin_data`` but NOT Garmin-gated — that pulls activities from
``IntervalsICUClient.list_activities`` and routes them through the SAME common
ingest funnel (``normalize_provider_activity(..., "intervals") → ingest_provider_batch``)
Garmin uses, via the provider-agnostic windowed runner (#280). No Garmin auth, no
wellness sync, no plan delivery — only activities (slice-spec §1 Non-goals).

Contract refinements enforced here (review round, slice-spec §3):

- **Database-first.** The core takes a ``Database``, not a Streamlit
  ``StateManager``. An API wrapper that binds a request's state/database is a
  separate step (§5); this module owns the provider logic only.
- **Preflight fail-fast.** ``client = client or get_client()``; then
  ``is_configured()`` is checked BEFORE any fetch/cursor work, raising
  ``IntervalsICUConfigurationError`` (not swallowed into a warning). The
  documented default ``athlete_id="0"`` is valid and never treated as missing.
- **Fail-closed provider response.** A 429 / network error, a malformed
  (non-list / non-mapping / id-less) response, or a normalization error all mark
  the chunk ``dirty`` (via ``ChunkFetch``) — a warning is recorded, the cursor is
  NOT advanced, and later chunks are not fetched. The data behind it is
  re-fetched idempotently on the next run (M0 ``UNIQUE`` + upsert). The provider
  error never propagates as an exception (matches the Garmin path's "external
  failures → warnings" contract).
- **Chunk-boundary dedup.** ``iter_chunks`` makes adjacent chunks share a
  boundary date, so a single activity can be returned by two chunks. Within ONE
  run, a ``seen`` set of ``provider_activity_id`` values ensures it is ingested
  exactly once (``ingested == new``, ``updated == 0``); the idempotent upsert
  then keeps cross-run repeats clean.
- **Historical override.** ``days=N`` (positive int) forces the EXACT window
  ``[now − N, now]`` with ``bootstrapped=False`` via the runner's
  ``window_days``; the monotonic ``set_sync_cursor`` never lets a replay lower
  the high-water boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from config.settings import Settings
from data.database import Database
from services.activity_ingest import (
    ProviderActivity,
    normalize_provider_activity,
)
from services.intervals_icu import (
    IntervalsICUClient,
    IntervalsICUConfigurationError,
    IntervalsICUError,
    get_client,
)
from services.sync import SyncProgressUpdate
from services.sync_cursor import (
    ChunkFetch,
    WindowedSyncResult,
    run_windowed_sync,
)

# Progress callback contract: ONE SyncProgressUpdate object, matching
# SyncJobManager._run_job's ``on_progress(update: SyncProgressUpdate)`` so the
# adapter drops into the existing sync-job runner in step 5 (§5) without a shape
# mismatch (review P1.1).
SyncProgressCallback = Callable[[SyncProgressUpdate], None]

# Intervals.icu caps a reconciliation window at 90 days, so each chunk fed to
# list_activities must be at most that wide (services/intervals_icu).
CHUNK_DAYS = 90


@dataclass
class IntervalsSyncResult:
    """Structured, UI-agnostic outcome of :func:`sync_intervals_data`.

    Mirrors the Garmin result's intent (new/updated/skipped + warnings) without
    the Garmin-only domains (HRV/sleep/health). ``new``/``updated`` come from
    ``canonical_created``; ``new + updated == ingested``; ``skipped`` is 0 while
    ``list_activities`` fails closed on id-less rows (no silent drops).
    """

    new: int = 0
    updated: int = 0
    skipped: int = 0
    ingested: int = 0
    warnings: list[str] = field(default_factory=list)
    source: str = "intervals"
    window_start: str = ""
    window_end: str = ""
    bootstrapped: bool = False
    halted: bool = False
    cursor_value: str | None = None


def _validate_days(days: Any) -> int | None:
    """``days`` is a positive int (historical override) or None (cursor window).
    A non-positive or non-int value fails fast rather than being coerced."""
    if days is None:
        return None
    # bool is an int subclass — reject it explicitly.
    if isinstance(days, bool) or not isinstance(days, int):
        raise ValueError(f"sync_intervals_data: days must be a positive int, got {days!r}")
    if days <= 0:
        raise ValueError(f"sync_intervals_data: days must be a positive int, got {days!r}")
    return days


def _build_fetch_chunk(
    client: IntervalsICUClient,
    seen: set[str],
) -> Callable[[datetime, datetime], ChunkFetch]:
    """Build the provider-specific ``fetch_chunk`` for the windowed runner.

    Every provider failure (429/network/malformed via ``list_activities``) and
    every normalization failure become a DIRTY chunk (warning recorded on the
    ChunkFetch, cursor unmoved), never an exception — matching the Garmin path.
    The ``seen`` set dedups a ``provider_activity_id`` returned by two adjacent
    chunks within one run, so it is ingested exactly once (chunk-boundary
    protection). (The unused ``warnings`` parameter was removed in review cleanup.)
    """

    def fetch_chunk(chunk_start: datetime, chunk_end: datetime) -> ChunkFetch:
        try:
            rows = client.list_activities(chunk_start.date(), chunk_end.date())
        except IntervalsICUError as exc:
            return ChunkFetch(dirty=True, warning=f"⚠️ Intervals.icu: {exc}")

        candidates: list[ProviderActivity] = []
        for row in rows:
            try:
                candidate = normalize_provider_activity(row, "intervals")
            except (ValueError, TypeError) as exc:
                return ChunkFetch(
                    dirty=True,
                    warning=f"⚠️ Intervals.icu normalization failed: {exc}",
                )
            if candidate.provider_activity_id in seen:
                continue  # already ingested this run (chunk-boundary dedup)
            seen.add(candidate.provider_activity_id)
            candidates.append(candidate)
        return ChunkFetch(candidates=candidates)

    return fetch_chunk


def sync_intervals_data(
    database: Database,
    *,
    days: int | None = None,
    now: datetime | None = None,
    on_progress: SyncProgressCallback | None = None,
    client: IntervalsICUClient | None = None,
    chunk_days: int = CHUNK_DAYS,
) -> IntervalsSyncResult:
    """Synchronize Intervals.icu activities into local storage (M1-T4).

    NOT Garmin-gated: the only gate is a configured Intervals.icu API key.
    Activities flow through the same common ingest as Garmin; the persistent
    cursor advances only after a whole clean chunk ingests (#280), so an abort
    mid-run leaves no data stranded behind it.

    Args:
        database: the local SQLite store (Database-first contract).
        days: optional positive int — explicit historical reload of
            ``[now − days, now]`` (``bootstrapped=False``); the high-water cursor
            never moves backward. ``None`` uses the cursor-derived window.
        now: injectable anchor (tests); defaults to ``datetime.now()``.
        on_progress: optional callback taking ONE ``SyncProgressUpdate`` — the
            same single-arg object contract ``SyncJobManager._run_job`` uses
            (review P1.1) — so the adapter drops into the existing sync-job
            runner unchanged in step 5 (§5). This slice does not wire it to a UI.
        client: optional ``IntervalsICUClient`` (tests inject a fake). Defaults
            to ``get_client()`` from settings.
        chunk_days: max width of a single fetch chunk (capped at the
            Intervals.icu reconciliation window). Tests narrow it to force
            multiple chunks.

    Raises:
        IntervalsICUConfigurationError: no API key configured (preflight).
        ValueError: ``days`` is not a positive int.
    """
    window_days = _validate_days(days)

    # Preflight (refinement): resolve the client, then fail fast on a missing
    # key BEFORE any fetch or cursor work. athlete_id="0" (the default) is valid.
    client = client or get_client()
    if not client.is_configured():
        raise IntervalsICUConfigurationError(
            "Intervals.icu не настроен. Укажите INTERVALS_ICU_API_KEY в .env."
        )

    if on_progress is not None:
        on_progress(
            SyncProgressUpdate(
                percent=10,
                message="📡 Загрузка активностей Intervals.icu...",
                step_text="Шаг 1/2: Получение активностей...",
            )
        )

    seen: set[str] = set()
    fetch_chunk = _build_fetch_chunk(client, seen)

    wsr: WindowedSyncResult = run_windowed_sync(
        database,
        "intervals",
        "activities",
        fetch_chunk=fetch_chunk,
        now=now,
        chunk_days=chunk_days,
        primary_source=Settings.PRIMARY_ACTIVITY_SOURCE,
        window_days=window_days,
    )

    if on_progress is not None:
        on_progress(
            SyncProgressUpdate(
                percent=100,
                message="✅ Готово" if not wsr.halted else "⚠️ Синк остановлен",
                step_text="Шаг 2/2: Завершение...",
            )
        )

    return IntervalsSyncResult(
        new=wsr.new,
        updated=wsr.updated,
        skipped=0,  # list_activities fails closed on id-less rows (no silent drops)
        ingested=wsr.ingested,
        warnings=list(wsr.warnings),
        window_start=wsr.window_start,
        window_end=wsr.window_end,
        bootstrapped=wsr.bootstrapped,
        halted=wsr.halted,
        cursor_value=wsr.cursor_value,
    )


__all__ = ["CHUNK_DAYS", "IntervalsSyncResult", "sync_intervals_data"]

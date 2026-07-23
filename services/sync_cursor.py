"""Provider-agnostic windowed sync runner + persistent-cursor window resolution (M1, #270).

Knows ONLY about time windows, chronological chunks, a monotonic per-provider/per-domain
cursor and two callbacks. Provider auth, the shape of provider rows, field mapping and
provider-namespace attribution live entirely in the adapter that supplies ``fetch_chunk``
(slice-spec §4/§5, review constraint 1) — this module never imports a provider client.

The cursor is the ISO-date HIGH-WATER boundary of the window a provider has fully AND
cleanly processed (not the last activity's date). It advances to a chunk's end ONLY via
the ``ingest_provider_batch`` advance callback, i.e. after that chunk's whole batch has
been ingested (constraint 3), and MONOTONICALLY (a historical replay never lowers it, §4).
A "dirty" chunk — any 429/network/partial-page the adapter flags — advances nothing and
stops every later chunk (constraint 2); the data behind it is re-fetched on the next run,
which is idempotent (M0 ``UNIQUE`` + upsert).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from data.database import parse_cursor_date
from services.activity_ingest import ProviderActivity, ingest_provider_batch


DATE_FMT = "%Y-%m-%d"


@dataclass(frozen=True)
class ChunkFetch:
    """One chunk's provider response, as the adapter reports it.

    ``dirty`` marks a NON-clean fetch (429, network error, partial page): the chunk must
    not advance the cursor and must stop later chunks (constraint 2). ``candidates`` are
    ignored when dirty. ``warning`` is a UI-agnostic message folded into the result.
    """

    candidates: list[ProviderActivity] = field(default_factory=list)
    dirty: bool = False
    warning: str | None = None


@dataclass
class WindowedSyncResult:
    """Outcome of :func:`run_windowed_sync` — structural, UI-agnostic.

    ``new``/``updated`` are an ADDITIVE breakdown of ``ingested`` derived from the
    ``canonical_created`` flag each ``write_provider_activity`` returns (M1 §3,
    §11 step 3): ``new`` counts activities whose canonical ``activities`` row was
    CREATED by the projection, ``updated`` those that already existed. The
    invariant ``new + updated == ingested`` always holds. Pre-M1 callers and the
    M1-T5 gates read ``ingested``/``cursor_value``/``halted`` and are unaffected.
    """

    window_start: str
    window_end: str
    bootstrapped: bool
    chunks_total: int = 0
    chunks_clean: int = 0
    ingested: int = 0
    new: int = 0
    updated: int = 0
    halted: bool = False
    cursor_value: str | None = None
    warnings: list[str] = field(default_factory=list)


def _to_date(value: datetime) -> str:
    return value.strftime(DATE_FMT)


def resolve_window_from_cursor(
    cursor_value: str | None,
    *,
    now: datetime,
    overlap_days: int,
    bootstrap_days: int,
) -> tuple[datetime, datetime, bool]:
    """Resolve the sync window from the persistent cursor.

    Cursor present → ``[cursor − overlap_days, now]``: the boundary day is re-synced on
    purpose to catch late-uploaded / edited activities, and the idempotent upsert (M0)
    absorbs the overlap without duplicates. Cursor ABSENT (fresh, or just reset) →
    bootstrap ``[now − bootstrap_days, now]``. Returns ``(start, end, bootstrapped)``.

    Fail-closed on a bad cursor (review P1): a present-but-invalid persisted cursor is an
    invariant violation and RAISES — never a silent bootstrap, which would both mask the
    corruption and, with the monotonic ``max``, re-bootstrap 90 days forever. A cursor
    AHEAD of ``now`` (clock rewind / corruption) likewise RAISES with a diagnostic rather
    than returning a false clean no-op (its window would be ``end < start`` → zero chunks,
    a "successful" sync that reads nothing). Only an ABSENT cursor bootstraps.
    """
    if not cursor_value:
        return now - timedelta(days=max(1, bootstrap_days)), now, True
    anchor = parse_cursor_date(cursor_value)  # invalid persisted cursor → invariant error
    if anchor > now.date():
        raise ValueError(
            f"sync cursor {anchor.isoformat()} is ahead of now {now.date().isoformat()} "
            "— refusing to sync (corrupt cursor or clock rewind); reset to re-bootstrap"
        )
    start = datetime(anchor.year, anchor.month, anchor.day) - timedelta(days=max(0, overlap_days))
    return start, now, False


def iter_chunks(start: datetime, end: datetime, chunk_days: int) -> list[tuple[datetime, datetime]]:
    """Split ``[start, end]`` into chronological chunks of at most ``chunk_days`` (oldest
    first). An empty (``start == end``) but valid window yields ONE zero-width boundary
    chunk, so a clean empty window still advances the cursor rather than re-syncing the
    same tail forever (§4)."""
    if end < start:
        return []
    span = max(1, int(chunk_days))
    chunks: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=span), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    if not chunks:
        chunks.append((start, end))
    return chunks


def run_windowed_sync(
    db: Any,
    provider: str,
    domain: str,
    *,
    fetch_chunk: Callable[[datetime, datetime], ChunkFetch],
    now: datetime | None = None,
    overlap_days: int = 1,
    bootstrap_days: int = 90,
    chunk_days: int = 90,
    primary_source: str | None = None,
    window_days: int | None = None,
) -> WindowedSyncResult:
    """Resolve the window from the persistent cursor, process it in chronological chunks,
    and advance the cursor to a chunk's end ONLY after that chunk's whole batch ingests.

    Constraint 2 (dirty halts): a chunk the adapter flags ``dirty`` records its warning,
    stops the run and leaves the cursor at the last CLEAN boundary — data behind it is
    re-fetched next run (idempotent). Constraint 3 (cursor via callback only): the cursor
    is written solely by the ``ingest_provider_batch`` advance callback, so it moves only
    after a full batch; a per-activity ingest failure propagates from
    ``ingest_provider_batch`` BEFORE the callback (cursor unmoved, M0 guardrail), and a
    cursor-write error is NOT swallowed. This runner stays provider-agnostic (constraint
    1): everything provider-specific is inside ``fetch_chunk``.

    ``window_days`` is an explicit historical-window override (M1 §11 step 3 refinement
    2): a positive int forces the EXACT window ``[now − window_days, now]`` — NOT the
    cursor-derived ``[cursor − overlap, now]`` — and marks it ``bootstrapped=False``
    (this is an explicit reload, not a fallback). The cursor stays MONOTONIC regardless:
    ``set_sync_cursor`` never lowers an existing high-water boundary, so a historical
    replay of an older window processes it but cannot pull the boundary backward. The
    "positive int" contract is enforced AT THIS BOUNDARY (review P1.3), not only in an
    adapter wrapper: a non-positive/float/bool/str value used to yield a FALSE success
    (``end < start`` → 0 chunks → ``halted=False``, no fetch) and now raises before any
    work, mirroring how :func:`resolve_window_from_cursor` fails closed on a bad cursor.
    """
    now = now or datetime.now()
    if window_days is not None:
        # Enforce the contract at the runner boundary (review P1.3): a bool is an int
        # subclass and is rejected explicitly; a non-int or non-positive int would
        # otherwise compute end<start → 0 chunks → a silent no-op "success".
        if isinstance(window_days, bool) or not isinstance(window_days, int) or window_days <= 0:
            raise ValueError(
                f"run_windowed_sync: window_days must be a positive int, got {window_days!r}"
            )
        # The override drives the START date, but the persisted cursor must still be
        # validated first (Codex review P2 / P1.4): without this a future or corrupt
        # cursor was never parsed/checked, so a historical run fetched from the
        # provider, "succeeded", and left the cursor at the future date — leaving
        # later incremental syncs broken. Symmetry with resolve_window_from_cursor's
        # fail-closed on future/corrupt cursors. An ABSENT cursor is fine (a fresh
        # store can still do an explicit reload).
        cursor_value = db.get_sync_cursor(provider, domain)
        if cursor_value:
            anchor = parse_cursor_date(cursor_value)  # corrupt → invariant error
            if anchor > now.date():
                raise ValueError(
                    f"sync cursor {anchor.isoformat()} is ahead of now {now.date().isoformat()} "
                    "— refusing to sync (corrupt cursor or clock rewind); reset to re-bootstrap"
                )
        # Explicit reload: exact [now-N, now], not a bootstrap/fallback.
        start = now - timedelta(days=window_days)
        end = now
        bootstrapped = False
    else:
        cursor_value = db.get_sync_cursor(provider, domain)
        start, end, bootstrapped = resolve_window_from_cursor(
            cursor_value, now=now, overlap_days=overlap_days, bootstrap_days=bootstrap_days
        )
    result = WindowedSyncResult(
        window_start=_to_date(start),
        window_end=_to_date(end),
        bootstrapped=bootstrapped,
    )
    chunks = iter_chunks(start, end, chunk_days)
    result.chunks_total = len(chunks)

    for chunk_start, chunk_end in chunks:
        fetch = fetch_chunk(chunk_start, chunk_end)
        if fetch.dirty:
            if fetch.warning:
                result.warnings.append(fetch.warning)
            result.halted = True
            break

        boundary = _to_date(chunk_end)

        def _advance(_boundary: str = boundary) -> None:
            # The cursor moves ONLY here — after ingest_provider_batch finished the whole
            # chunk (constraint 3). set_sync_cursor is monotonic, so a replay of an older
            # window never lowers the high-water mark (§4).
            db.set_sync_cursor(provider, domain, _boundary)

        batch = ingest_provider_batch(
            db,
            list(fetch.candidates),
            advance_cursor=_advance,
            primary_source=primary_source,
        )
        result.chunks_clean += 1
        result.ingested += len(batch.ingested)
        # Additive new/updated breakdown from canonical_created (M1 §3). Each
        # ingested item is the dict write_provider_activity returns; its
        # canonical_created flag is the same signal the Garmin path counts 1:1.
        for item in batch.ingested:
            if item.get("canonical_created"):
                result.new += 1
            else:
                result.updated += 1
        if fetch.warning:
            result.warnings.append(fetch.warning)

    result.cursor_value = db.get_sync_cursor(provider, domain)
    return result


__all__ = [
    "ChunkFetch",
    "WindowedSyncResult",
    "iter_chunks",
    "resolve_window_from_cursor",
    "run_windowed_sync",
]

"""M1 cursor slice — persistent cursor + provider-agnostic windowed runner (#270, §11 step 2).

Gate M1-T5 (cursor = processed-window boundary, not activity date):
  (a) re-syncing the same window → no duplicates, cursor stable (monotonic);
  (b) a clean but EMPTY window still advances the boundary;
  (c) a provider error on a chunk marks it dirty → cursor halts at the last clean
      boundary, later chunks are not fetched, data is re-fetched idempotently next run.

Plus the cursor primitives (monotonic set/get, per-key isolation) and window resolution
(bootstrap vs cursor). The runner stays provider-agnostic (review constraint 1): tests
drive it with a fake fetch_chunk, no Intervals client involved. M1-T8 (reset clears
cursors → bootstrap) lives beside the M0 reset gate in test_activity_ingest.py.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from data.database import Database
from services.activity_ingest import normalize_provider_activity
from services.sync_cursor import (
    ChunkFetch,
    iter_chunks,
    resolve_window_from_cursor,
    run_windowed_sync,
)


pytestmark = pytest.mark.smoke

NOW = datetime(2026, 7, 23)


def _garmin_candidate(activity_id: str):
    return normalize_provider_activity(
        {
            "activity_id": activity_id,
            "date": "2026-07-10",
            "sport": "cycling",
            "duration_minutes": 95.0,
            "source_tss": 86.0,
            "tss": 86.0,
            "tss_method": "power_np",
        },
        "garmin",
    )


def _activity_ids(db: Database) -> set:
    conn = sqlite3.connect(db.db_path)
    ids = {row[0] for row in conn.execute("SELECT activity_id FROM activities")}
    conn.close()
    return ids


def _orphan_count(db: Database) -> int:
    conn = sqlite3.connect(db.db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM activity_provider_links l "
        "LEFT JOIN activities a ON a.activity_id = l.canonical_activity_id "
        "WHERE a.activity_id IS NULL"
    ).fetchone()[0]
    conn.close()
    return count


# --- cursor primitives ---------------------------------------------------------

def test_set_sync_cursor_is_monotonic_and_isolated(tmp_path):
    db = Database(str(tmp_path / "cursor.db"))
    assert db.get_sync_cursor("intervals", "activities") is None

    assert db.set_sync_cursor("intervals", "activities", "2026-07-10") == "2026-07-10"
    assert db.get_sync_cursor("intervals", "activities") == "2026-07-10"

    # advance forward
    assert db.set_sync_cursor("intervals", "activities", "2026-07-15") == "2026-07-15"
    # a historical replay must NOT pull the high-water boundary backward
    assert db.set_sync_cursor("intervals", "activities", "2026-07-01") == "2026-07-15"
    assert db.get_sync_cursor("intervals", "activities") == "2026-07-15"

    # cursors are isolated per (provider, domain)
    assert db.get_sync_cursor("garmin", "activities") is None
    assert db.get_sync_cursor("intervals", "wellness") is None


def test_resolve_window_bootstrap_when_no_cursor():
    start, end, bootstrapped = resolve_window_from_cursor(
        None, now=NOW, overlap_days=1, bootstrap_days=90
    )
    assert bootstrapped is True
    assert start == NOW - timedelta(days=90)
    assert end == NOW


def test_resolve_window_from_cursor_applies_overlap():
    start, end, bootstrapped = resolve_window_from_cursor(
        "2026-07-20", now=NOW, overlap_days=1, bootstrap_days=90
    )
    assert bootstrapped is False
    assert start == datetime(2026, 7, 19)  # boundary day re-synced on purpose
    assert end == NOW


def test_iter_chunks_splits_chronologically():
    chunks = iter_chunks(datetime(2026, 4, 24), datetime(2026, 7, 23), 30)
    assert len(chunks) == 3
    assert chunks[0][0] == datetime(2026, 4, 24)
    assert chunks[-1][1] == datetime(2026, 7, 23)
    # contiguous, oldest-first, no gaps/overlaps
    for (a_start, a_end), (b_start, _b_end) in zip(chunks, chunks[1:]):
        assert a_end == b_start


# --- M1-T5 -------------------------------------------------------------------

def test_m1_t5b_empty_clean_window_still_advances_cursor(tmp_path):
    """A clean but EMPTY window advances the boundary to the window end (not to any
    activity date), so the tail is not re-synced forever."""
    db = Database(str(tmp_path / "empty.db"))
    calls: list[tuple] = []

    def fetch(chunk_start, chunk_end):
        calls.append((chunk_start, chunk_end))
        return ChunkFetch(candidates=[], dirty=False)  # clean, no activities

    result = run_windowed_sync(
        db, "intervals", "activities", fetch_chunk=fetch, now=NOW,
        overlap_days=1, bootstrap_days=90, chunk_days=90,
    )

    assert result.bootstrapped is True
    assert result.ingested == 0
    assert result.halted is False
    assert len(calls) == 1  # single 90-day chunk
    # cursor = window end (the boundary), not empty and not an activity date
    assert result.cursor_value == NOW.strftime("%Y-%m-%d")
    assert db.get_sync_cursor("intervals", "activities") == NOW.strftime("%Y-%m-%d")


def test_m1_t5a_resync_same_window_is_idempotent_and_cursor_stable(tmp_path):
    db = Database(str(tmp_path / "resync.db"))
    candidate = _garmin_candidate("555111")

    def fetch(chunk_start, chunk_end):
        return ChunkFetch(candidates=[candidate], dirty=False)

    run_windowed_sync(
        db, "garmin", "activities", fetch_chunk=fetch, now=NOW, chunk_days=90,
        primary_source="garmin",
    )
    ids_after_first = _activity_ids(db)
    cursor_after_first = db.get_sync_cursor("garmin", "activities")

    # Second run resolves its window from the cursor and re-ingests the same activity.
    run_windowed_sync(
        db, "garmin", "activities", fetch_chunk=fetch, now=NOW, chunk_days=90,
        primary_source="garmin",
    )

    assert ids_after_first == {"555111"}
    assert _activity_ids(db) == {"555111"}  # no duplicate
    assert db.get_sync_cursor("garmin", "activities") == cursor_after_first  # stable
    assert _orphan_count(db) == 0


def test_m1_t5c_dirty_chunk_halts_at_last_clean_boundary(tmp_path):
    """A provider error on the 2nd of 3 chunks makes it dirty: the cursor stops at the
    1st clean chunk's end, the 3rd chunk is never fetched, and the data behind the error
    is re-fetched (idempotently) on the next run."""
    db = Database(str(tmp_path / "dirty.db"))
    bootstrap_start = NOW - timedelta(days=90)
    first_clean_boundary = (bootstrap_start + timedelta(days=30)).strftime("%Y-%m-%d")
    fetched_ends: list[datetime] = []

    def fetch(chunk_start, chunk_end):
        fetched_ends.append(chunk_end)
        if len(fetched_ends) == 1:
            return ChunkFetch(candidates=[_garmin_candidate("111")], dirty=False)
        if len(fetched_ends) == 2:
            return ChunkFetch(dirty=True, warning="⚠️ Intervals 429 на чанке")
        return ChunkFetch(candidates=[_garmin_candidate("999")], dirty=False)  # must not run

    result = run_windowed_sync(
        db, "intervals", "activities", fetch_chunk=fetch, now=NOW,
        overlap_days=1, bootstrap_days=90, chunk_days=30, primary_source="garmin",
    )

    assert result.halted is True
    assert result.chunks_clean == 1
    assert len(fetched_ends) == 2  # 3rd chunk NOT fetched (stopped after dirty)
    assert any("429" in warning for warning in result.warnings)
    # cursor advanced only to the first clean chunk's end
    assert db.get_sync_cursor("intervals", "activities") == first_clean_boundary
    assert _activity_ids(db) == {"111"}  # only the first clean chunk's activity landed
    assert _orphan_count(db) == 0

    # Next run (all chunks clean) resumes from that boundary and completes without dups.
    def fetch_clean(chunk_start, chunk_end):
        return ChunkFetch(candidates=[_garmin_candidate("222")], dirty=False)

    retry = run_windowed_sync(
        db, "intervals", "activities", fetch_chunk=fetch_clean, now=NOW,
        overlap_days=1, bootstrap_days=90, chunk_days=30, primary_source="garmin",
    )
    assert retry.halted is False
    assert _activity_ids(db) == {"111", "222"}
    assert db.get_sync_cursor("intervals", "activities") == NOW.strftime("%Y-%m-%d")


def test_run_windowed_sync_does_not_mask_ingest_errors(tmp_path, monkeypatch):
    """Constraint 3: a per-activity ingest failure propagates (not swallowed) BEFORE the
    advance callback, so the cursor stays put (M0 batch guardrail)."""
    import services.activity_ingest as ingest

    db = Database(str(tmp_path / "ingest-error.db"))

    def boom(database, candidate, *, primary_source=None):
        raise RuntimeError("ingest exploded")

    # ingest_provider_batch calls the module-global ingest_provider_activity in
    # services.activity_ingest; patch it there so the batch actually raises.
    monkeypatch.setattr(ingest, "ingest_provider_activity", boom)

    def fetch(chunk_start, chunk_end):
        return ChunkFetch(candidates=[_garmin_candidate("111")], dirty=False)

    with pytest.raises(RuntimeError, match="ingest exploded"):
        run_windowed_sync(
            db, "intervals", "activities", fetch_chunk=fetch, now=NOW, chunk_days=90,
            primary_source="garmin",
        )

    assert db.get_sync_cursor("intervals", "activities") is None  # cursor unmoved

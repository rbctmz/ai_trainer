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
from datetime import date, datetime, timedelta

import pytest

from data.database import Database, parse_cursor_date
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


# --- P1: cursor is a validated ISO date; future/corrupt fails closed -----------

# Strict YYYY-MM-DD contract — VERSION-INDEPENDENT (review P1 round 2). The same shapes
# must be accepted/rejected identically at the parser, the DB-write boundary and the
# resolver. date.fromisoformat alone is not enough: on Python 3.11 it accepts basic-ISO
# `20260723` and ISO-week `2026-W30-4` that 3.10 rejects, and `.strip()` used to allow
# surrounding whitespace — so a strict shape guard is required.
_STRICT_ACCEPT = ["2026-07-23", "2026-01-01", "2000-12-31", "1999-12-09"]
_STRICT_REJECT = [
    "20260723",             # basic ISO, no dashes — 3.11 date.fromisoformat accepts it
    "2026-W30-4",           # ISO week date — 3.11 date.fromisoformat accepts it
    " 2026-07-23",          # leading whitespace
    "2026-07-23 ",          # trailing whitespace
    "2026-7-3",             # not zero-padded
    "2026/07/23",           # wrong separator
    "2026-13-45",           # not a real calendar date
    "2026-07-23T00:00:00",  # datetime string
    "garbage",
    "",
]


@pytest.mark.parametrize("value", _STRICT_ACCEPT)
def test_parse_cursor_date_accepts_strict_iso(value):
    assert parse_cursor_date(value).isoformat() == value


def test_parse_cursor_date_accepts_date_and_datetime_objects():
    assert parse_cursor_date(date(2026, 7, 23)).isoformat() == "2026-07-23"
    assert parse_cursor_date(datetime(2026, 7, 23, 10, 30)).isoformat() == "2026-07-23"


@pytest.mark.parametrize("value", _STRICT_REJECT)
def test_parse_cursor_date_rejects_non_strict(value):
    with pytest.raises(ValueError):
        parse_cursor_date(value)


@pytest.mark.parametrize("value", _STRICT_REJECT)
def test_set_sync_cursor_rejects_non_strict_at_write_boundary(tmp_path, value):
    db = Database(str(tmp_path / "reject.db"))
    with pytest.raises(ValueError):
        db.set_sync_cursor("intervals", "activities", value)
    assert db.get_sync_cursor("intervals", "activities") is None  # nothing stored


@pytest.mark.parametrize("value", [v for v in _STRICT_REJECT if v != ""])
def test_resolve_window_rejects_non_strict_at_resolver_boundary(value):
    with pytest.raises(ValueError):
        resolve_window_from_cursor(value, now=NOW, overlap_days=1, bootstrap_days=90)


def test_resolve_window_treats_empty_cursor_as_absent():
    # An empty string is "no cursor" (get_sync_cursor already maps '' → None), so the
    # resolver bootstraps rather than raising — distinct from a malformed non-empty value.
    _start, _end, bootstrapped = resolve_window_from_cursor(
        "", now=NOW, overlap_days=1, bootstrap_days=90
    )
    assert bootstrapped is True


def test_set_sync_cursor_normalizes_accepted_values(tmp_path):
    db = Database(str(tmp_path / "accept.db"))
    assert db.set_sync_cursor("intervals", "activities", "2026-07-05") == "2026-07-05"
    assert db.set_sync_cursor("intervals", "wellness", date(2026, 8, 1)) == "2026-08-01"


def test_resolve_window_rejects_future_cursor():
    """A cursor ahead of ``now`` (clock rewind / corruption) must NOT resolve to a
    false clean no-op (end < start → 0 chunks): fail closed with a diagnostic."""
    with pytest.raises(ValueError, match="ahead of now"):
        resolve_window_from_cursor("2099-01-01", now=NOW, overlap_days=1, bootstrap_days=90)


def test_m1_future_cursor_fails_closed_in_runner(tmp_path):
    """Repro from review: cursor 2099-01-01 with now=2026-07-23 used to give fetch=0,
    chunks=0, halted=False — a sync that 'succeeds' while reading nothing. Now the runner
    raises before any fetch and the cursor is left untouched."""
    db = Database(str(tmp_path / "future.db"))
    db.set_sync_cursor("intervals", "activities", "2099-01-01")  # valid date, in the future
    fetch_calls: list = []

    def fetch(chunk_start, chunk_end):
        fetch_calls.append((chunk_start, chunk_end))
        return ChunkFetch(candidates=[], dirty=False)

    with pytest.raises(ValueError, match="ahead of now"):
        run_windowed_sync(
            db, "intervals", "activities", fetch_chunk=fetch, now=NOW,
            overlap_days=1, bootstrap_days=90, chunk_days=90,
        )

    assert fetch_calls == []  # no false-success sync
    assert db.get_sync_cursor("intervals", "activities") == "2099-01-01"  # untouched


def test_m1_corrupt_persisted_cursor_fails_closed_in_runner(tmp_path):
    """A corrupt cursor that somehow bypassed the write guard is caught on the read path:
    the runner raises rather than silently bootstrapping (and re-bootstrapping forever)."""
    db = Database(str(tmp_path / "corrupt.db"))
    conn = sqlite3.connect(db.db_path)
    conn.execute(
        "INSERT INTO sync_cursors (provider, domain, cursor_value) VALUES (?, ?, ?)",
        ("intervals", "activities", "garbage"),
    )
    conn.commit()
    conn.close()

    fetch_calls: list = []

    def fetch(chunk_start, chunk_end):
        fetch_calls.append(1)
        return ChunkFetch(candidates=[], dirty=False)

    with pytest.raises(ValueError):
        run_windowed_sync(
            db, "intervals", "activities", fetch_chunk=fetch, now=NOW, chunk_days=90,
        )
    assert fetch_calls == []


# --- P2: cursor-write failure propagates; data safe; idempotent retry ----------

def test_m1_cursor_write_error_propagates_and_leaves_data_recoverable(tmp_path, monkeypatch):
    """Review constraint 3 (now gated): the batch commits the activity, then
    set_sync_cursor fails → the exception surfaces (not masked), the activity/link stay
    committed, the cursor never appears, and a retry is idempotent (no duplicates)."""
    db = Database(str(tmp_path / "cursor-write.db"))

    def failing_set(provider, domain, cursor_value):
        raise RuntimeError("cursor write failed")

    monkeypatch.setattr(db, "set_sync_cursor", failing_set)

    def fetch(chunk_start, chunk_end):
        return ChunkFetch(candidates=[_garmin_candidate("111")], dirty=False)

    with pytest.raises(RuntimeError, match="cursor write failed"):
        run_windowed_sync(
            db, "intervals", "activities", fetch_chunk=fetch, now=NOW, chunk_days=90,
            primary_source="garmin",
        )

    # activity committed before the (failed) cursor write; cursor never appeared
    assert _activity_ids(db) == {"111"}
    assert _orphan_count(db) == 0
    monkeypatch.undo()  # restore the real set_sync_cursor
    assert db.get_sync_cursor("intervals", "activities") is None

    # retry now succeeds, idempotently (no duplicate activity), cursor lands
    retry = run_windowed_sync(
        db, "intervals", "activities", fetch_chunk=fetch, now=NOW, chunk_days=90,
        primary_source="garmin",
    )
    assert retry.halted is False
    assert _activity_ids(db) == {"111"}  # no duplicate
    assert db.get_sync_cursor("intervals", "activities") == NOW.strftime("%Y-%m-%d")

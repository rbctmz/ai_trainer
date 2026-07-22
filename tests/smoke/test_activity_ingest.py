"""Common activity ingest contract (ADR-0008 / #269, M0).

Covers the four M0-mandatory matrices:
  1. Order-independence: Garmin→Intervals ≡ Intervals→Garmin (canonical row, tss,
     source_tss, both links), for primary=garmin and primary=intervals.
  2. Backfill classification stability: garmin/demo/legacy_unknown, idempotent.
  3. Batch-cursor guardrail: a batch whose 2nd activity fails leaves the cursor
     put; retry processes both without duplicates; cursor advances only on full
     success (ADR-0008 п.5/п.8).
  4. Ingest-level no-orphan: the public ingest never leaves a link without its
     canonical, even though raw SQL admits such an orphan.
"""
from __future__ import annotations

import sqlite3

import pytest

import services.activity_ingest as ingest
from data.database import Database
from services.activity_ingest import (
    backfill_provider_links,
    classify_activity_id,
    ingest_provider_activity,
    ingest_provider_batch,
    normalize_provider_activity,
)


def _garmin_row(activity_id: str = "555111") -> dict:
    return {
        "activity_id": activity_id,
        "date": "2026-07-10",
        "sport": "cycling",
        "duration_minutes": 95.0,
        "distance_km": 38.2,
        "avg_hr": 141,
        "source_tss": 86.0,
        "tss": 86.0,
        "tss_method": "power_np",
        "garmin_training_load": 120.0,
    }


def _intervals_row(
    intervals_id: str = "i_777",
    external_id: str | None = "555111",
    source: str | None = "GARMIN_CONNECT",
    **overrides,
) -> dict:
    row = {
        "id": intervals_id,
        "external_id": external_id,
        "source": source,
        "start_date": "2026-07-10T04:30:00Z",  # UTC
        "start_date_local": "2026-07-10T06:30:00",  # local wall clock
        "type": "Ride",
        "name": "Morning Ride",
        "icu_training_load": 90,
        "moving_time": 5700,  # 95 min
    }
    row.update(overrides)
    return row


def _snapshot(path: str) -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    activities = [
        dict(row)
        for row in conn.execute(
            "SELECT activity_id, date, sport, duration_minutes, source_tss, tss, tss_method "
            "FROM activities ORDER BY activity_id"
        )
    ]
    links = [
        dict(row)
        for row in conn.execute(
            "SELECT canonical_activity_id, provider, provider_activity_id, external_provider, "
            "external_id, provider_tss, match_status FROM activity_provider_links "
            "ORDER BY provider, provider_activity_id"
        )
    ]
    conn.close()
    return {"activities": activities, "links": links}


def _orphan_count(path: str) -> int:
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT COUNT(*) FROM activity_provider_links l "
        "LEFT JOIN activities a ON a.activity_id = l.canonical_activity_id "
        "WHERE a.activity_id IS NULL"
    ).fetchone()
    conn.close()
    return row[0]


def _activity_ids(path: str) -> set:
    conn = sqlite3.connect(path)
    ids = {row[0] for row in conn.execute("SELECT activity_id FROM activities")}
    conn.close()
    return ids


# --- 1. normalize shapes -------------------------------------------------------

def test_normalize_garmin_self_anchors_in_garmin_namespace():
    candidate = normalize_provider_activity(_garmin_row(), "garmin")
    assert candidate.provider == "garmin"
    assert candidate.provider_activity_id == "555111"
    assert candidate.canonical_activity_id == "555111"
    assert (candidate.external_provider, candidate.external_id) == ("garmin", "555111")
    assert candidate.provider_tss == 86.0


def test_normalize_intervals_references_garmin_source_and_marks_fallback():
    candidate = normalize_provider_activity(_intervals_row(), "intervals")
    assert candidate.provider == "intervals"
    assert candidate.provider_activity_id == "i_777"
    # Garmin-sourced Intervals activity → same canonical id Garmin would use.
    assert candidate.canonical_activity_id == "555111"
    assert (candidate.external_provider, candidate.external_id) == ("garmin", "555111")
    assert candidate.provider_tss == 90.0
    assert candidate.canonical["sport"] == "cycling"  # "Ride" → cycling
    assert candidate.canonical["duration_minutes"] == 95.0
    # No local streams → provider load used as canonical tss, EXPLICITLY marked.
    assert candidate.canonical["tss_method"] == "intervals_icu_provider_fallback"


def test_normalize_intervals_records_utc_not_local_time():
    # blocker #5: local wall clock must not be stored in a *_utc column.
    candidate = normalize_provider_activity(_intervals_row(), "intervals")
    assert candidate.canonical["started_at_utc"] == "2026-07-10T04:30:00Z"
    assert candidate.canonical["date"] == "2026-07-10"  # local date is fine
    # Missing UTC field → None, never the local timestamp.
    no_utc = normalize_provider_activity(_intervals_row(start_date=None), "intervals")
    assert no_utc.canonical["started_at_utc"] is None


def test_normalize_intervals_local_first_tss_not_bypassed():
    # blocker #6: a locally-resolved tss is honoured; only a bare row falls back.
    local = normalize_provider_activity(
        _intervals_row(tss=71.5, tss_method="power_tss_bike"), "intervals"
    )
    assert local.canonical["tss"] == 71.5
    assert local.canonical["tss_method"] == "power_tss_bike"
    bare = normalize_provider_activity(_intervals_row(), "intervals")
    assert bare.canonical["tss_method"] == "intervals_icu_provider_fallback"


def test_normalize_intervals_non_garmin_source_keeps_its_own_namespace():
    # blocker #1: a Strava external_id must NOT be treated as a Garmin id.
    candidate = normalize_provider_activity(
        _intervals_row(external_id="555111", source="STRAVA"), "intervals"
    )
    assert candidate.external_provider == "strava"
    assert candidate.canonical_activity_id == "intervals_i_777"  # standalone, not 555111


def test_normalize_intervals_unknown_source_is_fail_closed_standalone():
    # blocker #1: without a source we cannot attribute external_id → no coordinate.
    candidate = normalize_provider_activity(
        _intervals_row(external_id="555111", source=None), "intervals"
    )
    assert candidate.external_provider is None and candidate.external_id is None
    assert candidate.canonical_activity_id == "intervals_i_777"


def test_normalize_intervals_without_external_id_is_standalone():
    candidate = normalize_provider_activity(_intervals_row(external_id=None), "intervals")
    assert candidate.external_provider is None and candidate.external_id is None
    assert candidate.canonical_activity_id == "intervals_i_777"


def test_normalize_unknown_source_fails_fast():
    with pytest.raises(ValueError):
        normalize_provider_activity(_garmin_row(), "strava")


# --- 2. order-independence (REQUIRED matrix) ----------------------------------

@pytest.mark.parametrize(
    "primary, expected_tss, expected_method",
    [
        ("garmin", 86.0, "power_np"),
        ("intervals", 90.0, "intervals_icu_provider_fallback"),
    ],
)
def test_order_independent_two_source_merge(tmp_path, primary, expected_tss, expected_method):
    garmin = normalize_provider_activity(_garmin_row(), "garmin")
    intervals = normalize_provider_activity(_intervals_row(), "intervals")

    forward = str(tmp_path / "forward.db")
    reverse = str(tmp_path / "reverse.db")
    db_forward = Database(forward)
    db_reverse = Database(reverse)

    # Garmin → Intervals
    ingest_provider_activity(db_forward, garmin, primary_source=primary)
    ingest_provider_activity(db_forward, intervals, primary_source=primary)
    # Intervals → Garmin
    ingest_provider_activity(db_reverse, intervals, primary_source=primary)
    ingest_provider_activity(db_reverse, garmin, primary_source=primary)

    snap_forward = _snapshot(forward)
    assert snap_forward == _snapshot(reverse), "arrival order must not change the result"

    # One canonical, anchored on the Garmin id regardless of primary.
    assert [a["activity_id"] for a in snap_forward["activities"]] == ["555111"]
    canonical = snap_forward["activities"][0]
    assert canonical["tss"] == expected_tss
    assert canonical["source_tss"] == expected_tss
    assert canonical["tss_method"] == expected_method

    # Two links, both matched, provider_tss kept per-link (native loads differ).
    links = {link["provider"]: link for link in snap_forward["links"]}
    assert set(links) == {"garmin", "intervals"}
    assert links["garmin"]["provider_tss"] == 86.0
    assert links["intervals"]["provider_tss"] == 90.0
    assert links["garmin"]["match_status"] == "matched"
    assert links["intervals"]["match_status"] == "matched"
    assert links["intervals"]["external_id"] == "555111"

    assert _orphan_count(forward) == 0


# --- 3. no-orphan invariant (REQUIRED guardrail) ------------------------------

def test_public_ingest_never_orphans_link(tmp_path):
    path = str(tmp_path / "orphan.db")
    db = Database(path)
    ingest_provider_activity(
        db, normalize_provider_activity(_garmin_row(), "garmin"), primary_source="garmin"
    )
    # Link and canonical were written together; no orphan exists.
    assert _orphan_count(path) == 0
    conn = sqlite3.connect(path)
    link_canonical = conn.execute(
        "SELECT canonical_activity_id FROM activity_provider_links"
    ).fetchone()[0]
    has_canonical = conn.execute(
        "SELECT 1 FROM activities WHERE activity_id=?", (link_canonical,)
    ).fetchone()
    conn.close()
    assert has_canonical is not None


# --- fail-closed matching + load integrity (blockers #1–#4) -------------------

def test_non_garmin_intervals_does_not_merge_with_same_garmin_id(tmp_path):
    # blocker #1: a Strava external_id equal to a Garmin id must not false-merge.
    path = str(tmp_path / "nomerge.db")
    db = Database(path)
    ingest_provider_activity(
        db, normalize_provider_activity(_garmin_row("555111"), "garmin"), primary_source="garmin"
    )
    strava = normalize_provider_activity(
        _intervals_row(external_id="555111", source="STRAVA"), "intervals"
    )
    ingest_provider_activity(db, strava, primary_source="garmin")

    snap = _snapshot(path)
    assert {a["activity_id"] for a in snap["activities"]} == {"555111", "intervals_i_777"}
    links = {link["provider"]: link for link in snap["links"]}
    assert links["garmin"]["match_status"] == "unmatched"
    assert links["intervals"]["canonical_activity_id"] == "intervals_i_777"
    assert links["intervals"]["external_provider"] == "strava"
    assert _orphan_count(path) == 0


def test_ambiguous_second_claimant_is_flagged_not_merged(tmp_path):
    # blocker #2: two Intervals activities claiming the same Garmin id → the second
    # is flagged 'ambiguous' and kept standalone, never silently merged.
    path = str(tmp_path / "ambiguous.db")
    db = Database(path)
    first = normalize_provider_activity(
        _intervals_row(intervals_id="i_A", external_id="555111"), "intervals"
    )
    second = normalize_provider_activity(
        _intervals_row(intervals_id="i_B", external_id="555111"), "intervals"
    )
    ingest_provider_activity(db, first, primary_source="garmin")
    ingest_provider_activity(db, second, primary_source="garmin")

    by_pid = {link["provider_activity_id"]: link for link in _snapshot(path)["links"]}
    assert by_pid["i_A"]["canonical_activity_id"] == "555111"
    assert by_pid["i_B"]["canonical_activity_id"] == "intervals_i_B"
    assert by_pid["i_B"]["match_status"] == "ambiguous"
    assert _orphan_count(path) == 0


def test_external_identity_change_does_not_double_count(tmp_path):
    # blocker #3: re-pairing an Intervals-only activity must drop its stale canonical.
    path = str(tmp_path / "identity.db")
    db = Database(path)
    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id="G1"), "intervals"),
        primary_source="garmin",
    )
    assert _activity_ids(path) == {"G1"}
    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id="G2"), "intervals"),
        primary_source="garmin",
    )
    assert _activity_ids(path) == {"G2"}  # G1 gone → load not doubled
    assert len(_snapshot(path)["links"]) == 1
    assert _orphan_count(path) == 0


def test_external_identity_change_keeps_canonical_with_other_links(tmp_path):
    # blocker #3 (converse): a canonical that still has a Garmin link is retained.
    path = str(tmp_path / "identity2.db")
    db = Database(path)
    ingest_provider_activity(
        db, normalize_provider_activity(_garmin_row("G1"), "garmin"), primary_source="garmin"
    )
    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id="G1"), "intervals"),
        primary_source="garmin",
    )
    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id="G2"), "intervals"),
        primary_source="garmin",
    )
    assert _activity_ids(path) == {"G1", "G2"}
    links = {link["provider"]: link for link in _snapshot(path)["links"]}
    assert links["garmin"]["canonical_activity_id"] == "G1"
    assert links["garmin"]["match_status"] == "unmatched"  # Intervals partner left
    assert links["intervals"]["canonical_activity_id"] == "G2"
    assert _orphan_count(path) == 0


def test_clear_all_data_clears_provider_links(tmp_path):
    # blocker #4: reset must not leave orphan links that double-count on next sync.
    path = str(tmp_path / "reset.db")
    db = Database(path)
    ingest_provider_activity(
        db, normalize_provider_activity(_garmin_row("555111"), "garmin"), primary_source="garmin"
    )
    assert len(_snapshot(path)["links"]) == 1
    db.clear_all_data()
    snap = _snapshot(path)
    assert snap["activities"] == [] and snap["links"] == []


def test_write_provider_activity_rolls_back_atomically(tmp_path):
    """Permanent guard: a failing canonical write leaves 0 activities / 0 links —
    the link is never committed without its canonical (ADR-0008 п.5)."""
    path = str(tmp_path / "rollback.db")
    db = Database(path)
    candidate = normalize_provider_activity(_garmin_row("555111"), "garmin")

    # Make `activities` unreachable so the canonical write fails AFTER the link insert.
    raw = sqlite3.connect(path)
    raw.execute("ALTER TABLE activities RENAME TO activities_hidden")
    raw.commit()
    raw.close()

    with pytest.raises(sqlite3.OperationalError):
        ingest_provider_activity(db, candidate, primary_source="garmin")

    raw = sqlite3.connect(path)
    assert raw.execute("SELECT COUNT(*) FROM activity_provider_links").fetchone()[0] == 0
    raw.execute("ALTER TABLE activities_hidden RENAME TO activities")
    assert raw.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0
    raw.close()


# --- 4. batch-cursor guardrail (REQUIRED matrix) ------------------------------

def test_batch_cursor_holds_on_failure_and_advances_on_full_success(tmp_path, monkeypatch):
    path = str(tmp_path / "batch.db")
    db = Database(path)

    cand_a = normalize_provider_activity(_garmin_row("111"), "garmin")
    cand_b = normalize_provider_activity(_garmin_row("222"), "garmin")

    cursor = {"value": "start"}

    def advance() -> None:
        cursor["value"] = "2026-07-11"

    # Inject a transient failure on the 2nd activity, once.
    real_ingest = ingest.ingest_provider_activity
    state = {"failed_once": False}

    def flaky(db, candidate, *, primary_source=None):
        if candidate.provider_activity_id == "222" and not state["failed_once"]:
            state["failed_once"] = True
            raise RuntimeError("injected transient failure on 2nd activity")
        return real_ingest(db, candidate, primary_source=primary_source)

    monkeypatch.setattr(ingest, "ingest_provider_activity", flaky)

    with pytest.raises(RuntimeError):
        ingest_provider_batch(
            db, [cand_a, cand_b], advance_cursor=advance, primary_source="garmin"
        )

    # Cursor did NOT move; first activity committed, second not.
    assert cursor["value"] == "start"
    assert _activity_ids(path) == {"111"}

    # Retry processes both without duplicates; cursor advances only now.
    result = ingest_provider_batch(
        db, [cand_a, cand_b], advance_cursor=advance, primary_source="garmin"
    )
    assert result.cursor_advanced is True
    assert cursor["value"] == "2026-07-11"
    assert _activity_ids(path) == {"111", "222"}  # 111 not duplicated
    assert len(_snapshot(path)["links"]) == 2
    assert _orphan_count(path) == 0


# --- 5. backfill classification + idempotency (REQUIRED matrix) ---------------

def test_backfill_classifies_and_is_idempotent(tmp_path):
    path = str(tmp_path / "backfill.db")
    db = Database(path)
    db.save_activities(
        [
            {"activity_id": "987654", "date": "2026-07-01", "source_tss": 100.0},
            {"activity_id": "demo_activity_20260701_0", "date": "2026-07-01", "source_tss": 40.0},
            {"activity_id": "legacy_thing_1", "date": "2026-07-01", "source_tss": None},
        ]
    )

    counts = backfill_provider_links(db)
    assert counts["garmin"] == 1
    assert counts["demo"] == 1
    assert counts["legacy_unknown"] == 1
    assert counts["skipped_existing"] == 0

    first = _snapshot(path)["links"]
    by_canonical = {link["canonical_activity_id"]: link for link in first}
    assert by_canonical["987654"]["provider"] == "garmin"
    assert by_canonical["987654"]["provider_tss"] == 100.0
    assert by_canonical["987654"]["external_id"] is None  # offline: no network lookup
    assert by_canonical["demo_activity_20260701_0"]["provider"] == "demo"
    assert by_canonical["legacy_thing_1"]["provider"] == "legacy_unknown"

    # Re-run: nothing new, classification stable (idempotent).
    recounts = backfill_provider_links(db)
    assert recounts == {"garmin": 0, "demo": 0, "legacy_unknown": 0, "skipped_existing": 3}
    assert _snapshot(path)["links"] == first
    assert _orphan_count(path) == 0


def test_classify_activity_id_shapes():
    assert classify_activity_id("1234567890") == "garmin"
    assert classify_activity_id("demo_activity_20260101_2") == "demo"
    assert classify_activity_id("test_thing") == "legacy_unknown"
    assert classify_activity_id("") == "legacy_unknown"

"""M1 common-ingest gates — slice D1 (#270).

Proves the Garmin persistence rewrite (services/sync.py::_sync_activities now flows
through services.activity_ingest instead of the legacy bulk database.sync_activities):

  - M1-T3  : the Garmin SUCCESS path is byte-identical EXCEPT the single additive
             field `source` (docs/intervals_primary_m1_slice_spec.md §2/§7).
  - M1-T3b : the failure path is DELIBERATELY changed — per-activity atomic ingest,
             so a failure mid-batch is rolled back whole, folded into warnings, and
             the sync CONTINUES with the rest; a retry is idempotent.
  - M1-T3c : the new/updated/skipped count matrix stays 1:1 with the legacy
             sync_activities — counted by activities-ROW existence (canonical_created),
             not by provider-link existence.

Row-level byte-identity of the stored activity is exercised richly by
tests/smoke/test_activity_tss_reconciliation.py (real Database, stored TSS/date read
back); internal atomic rollback of a partial write is a permanent M0 gate
(tests/smoke/test_activity_ingest.py). These tests focus on the sync-level contract.
"""
from __future__ import annotations

import sqlite3

import pytest

from data.data_processor import ActivityProcessor, resolve_athlete_ftp_lthr
from data.database import Database
from services import sync as sync_service
from services.activity_ingest import ingest_provider_activity, normalize_provider_activity
from services.sync import GarminSyncResult, _sync_activities, build_sync_status_payload


pytestmark = pytest.mark.smoke


# --- fixtures / helpers --------------------------------------------------------

def _garmin_activity(activity_id: str, *, sport: str = "running", load: float = 47.4) -> dict:
    """A raw Garmin-client activity (pre ActivityProcessor), as sync consumes."""
    return {
        "activityId": activity_id,
        "startTimeLocal": "2026-07-10T10:00:00",
        "startTimeGMT": "2026-07-10T07:00:00",
        "activityType": {"typeKey": sport},
        "duration": 3600,
        "movingDuration": 3420,
        "distance": 10000,
        "averageHR": 150,
        "activityTrainingLoad": load,
    }


def _null_id_activity() -> dict:
    """A raw activity whose activityId is present-but-null → must be skipped.

    (A *missing* activityId is defaulted to a synthetic timestamp id by
    ActivityProcessor and would NOT be skipped, so the null must be explicit.)
    """
    row = _garmin_activity("unused")
    row["activityId"] = None
    return row


def _intervals_row(intervals_id: str, garmin_id: str) -> dict:
    return {
        "id": intervals_id,
        "external_id": garmin_id,
        "source": "GARMIN_CONNECT",
        "start_date": "2026-07-12T05:00:00Z",
        "start_date_local": "2026-07-12T07:00:00",
        "type": "Ride",
        "name": "Morning Ride",
        "icu_training_load": 60,
        "moving_time": 3600,
    }


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


def _links_for(db: Database, canonical_id: str) -> list[tuple]:
    conn = sqlite3.connect(db.db_path)
    rows = conn.execute(
        "SELECT provider, provider_activity_id, canonical_activity_id "
        "FROM activity_provider_links WHERE canonical_activity_id=? ORDER BY provider",
        (canonical_id,),
    ).fetchall()
    conn.close()
    return rows


def _legacy_counts(db: Database, raw_activities: list[dict]) -> dict:
    """Reproduce the PRE-M1 _sync_activities: process → resolve_tss → the legacy bulk
    database.sync_activities. Used as the before/after oracle for the count matrix."""
    df = ActivityProcessor.process_activities(raw_activities)
    if df.empty:
        return {"new": 0, "updated": 0, "skipped": 0}
    ftp, lthr = resolve_athlete_ftp_lthr(db)
    resolved = []
    for _, row in df.iterrows():
        activity = row.to_dict()
        activity.update(ActivityProcessor.resolve_tss(activity, ftp=ftp, lthr=lthr))
        resolved.append(activity)
    return db.sync_activities(resolved)


# --- M1-T3 : success payload adds ONLY `source` -------------------------------

_LEGACY_PAYLOAD_KEYS = {
    "sync_state",
    "severity",
    "title",
    "summary",
    "synced_at",
    "days",
    "mode",
    "counts",
    "activity_changes",
    "recovery_changes",
    "highlights",
    "notices",
}


def test_m1_t3_sync_status_payload_adds_only_source_key():
    result = GarminSyncResult(activity_result={"new": 2, "updated": 1, "skipped": 0})
    payload = build_sync_status_payload(result, days=30)

    # The sole difference vs. the pre-M1 payload is the additive `source` key.
    assert set(payload) - _LEGACY_PAYLOAD_KEYS == {"source"}
    assert _LEGACY_PAYLOAD_KEYS - set(payload) == set()
    assert payload["source"] == "garmin"


def test_m1_t3_garmin_result_defaults_to_source_garmin():
    assert GarminSyncResult().source == "garmin"


# --- M1-T3b : failure mid-batch continues, atomic, idempotent retry -----------

def test_m1_t3b_failure_midbatch_continues_and_leaves_no_orphan(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "t3b.db"))
    activities = [_garmin_activity("1001"), _garmin_activity("1002"), _garmin_activity("1003")]

    real_ingest = sync_service.ingest_provider_activity

    def flaky_ingest(database, candidate, *, primary_source=None):
        if candidate.provider_activity_id == "1002":
            raise RuntimeError("injected ingest failure on 1002")
        return real_ingest(database, candidate, primary_source=primary_source)

    monkeypatch.setattr(sync_service, "ingest_provider_activity", flaky_ingest)

    warnings: list[str] = []
    counts = _sync_activities(db, activities, warnings=warnings)

    # A and C accepted; B failed. C proves continue-AFTER-error (not merely up-to-error).
    assert counts == {"new": 2, "updated": 0, "skipped": 0}
    assert _activity_ids(db) == {"1001", "1003"}
    # B left no trace at all — no activity, no orphan link (M0 atomicity).
    assert _orphan_count(db) == 0
    assert len(warnings) == 1
    assert "1002" in warnings[0]

    # Retry with the failure removed is idempotent: A,C already exist → updated;
    # B is finally created; no duplicates (UNIQUE + upsert).
    monkeypatch.setattr(sync_service, "ingest_provider_activity", real_ingest)
    retry = _sync_activities(db, activities)
    assert retry == {"new": 1, "updated": 2, "skipped": 0}
    assert _activity_ids(db) == {"1001", "1002", "1003"}
    assert _orphan_count(db) == 0


# --- M1-T3c : new/updated/skipped matrix == legacy sync_activities -------------

def test_m1_t3c_counts_match_legacy_sync_activities(tmp_path):
    """(а) first sync, (б) repeat, (в) mixed — 1:1 with the legacy bulk write."""
    new_db = Database(str(tmp_path / "t3c-new.db"))
    legacy_db = Database(str(tmp_path / "t3c-legacy.db"))

    first = [_garmin_activity("9001"), _garmin_activity("9002"), _null_id_activity()]
    repeat = [_garmin_activity("9001"), _garmin_activity("9002")]
    mixed = [_garmin_activity("9003"), _garmin_activity("9001")]

    # Each batch is applied to new_db exactly once (in lockstep with legacy_db), so
    # both databases evolve identically and the counts must match step for step.
    counts_first = _sync_activities(new_db, first)
    assert counts_first == {"new": 2, "updated": 0, "skipped": 1}
    assert counts_first == _legacy_counts(legacy_db, first)

    counts_repeat = _sync_activities(new_db, repeat)
    assert counts_repeat == {"new": 0, "updated": 2, "skipped": 0}
    assert counts_repeat == _legacy_counts(legacy_db, repeat)

    counts_mixed = _sync_activities(new_db, mixed)
    assert counts_mixed == {"new": 1, "updated": 1, "skipped": 0}
    assert counts_mixed == _legacy_counts(legacy_db, mixed)


def test_m1_t3c_existing_canonical_without_link_counts_updated(tmp_path):
    """(г) A legacy activities row with NO provider-link, ingested from Garmin, is
    `updated` (canonical_created=False) — counted by row existence, not link
    existence. If it counted by link, the brand-new garmin link would read as `new`."""
    db = Database(str(tmp_path / "t3c-legacy-row.db"))

    # Legacy bulk write: creates the activities row, leaves no provider-link.
    db.sync_activities(
        [
            {
                "activity_id": "3001",
                "date": "2026-07-11",
                "sport": "cycling",
                "source_tss": 50.0,
                "tss": 50.0,
                "tss_method": "power_np",
            }
        ]
    )
    assert "3001" in _activity_ids(db)
    assert _links_for(db, "3001") == []

    counts = _sync_activities(db, [_garmin_activity("3001", sport="cycling")])

    assert counts == {"new": 0, "updated": 1, "skipped": 0}
    assert _links_for(db, "3001") == [("garmin", "3001", "3001")]


def test_m1_t3c_intervals_first_then_garmin_counts_new_without_duplication(tmp_path):
    """(д) An Intervals copy first creates a standalone `intervals_<id>` canonical;
    the later Garmin activity gets a BRAND-NEW canonical `G` and counts `new` (not
    updated), and the standalone is absorbed — no duplicate canonical, no double load."""
    db = Database(str(tmp_path / "t3c-intervals-first.db"))

    candidate = normalize_provider_activity(_intervals_row("iv9", "4001"), "intervals")
    ingest_provider_activity(db, candidate, primary_source="garmin")

    # Standalone intervals canonical exists; the Garmin coordinate does not yet.
    assert "intervals_iv9" in _activity_ids(db)
    assert "4001" not in _activity_ids(db)

    counts = _sync_activities(db, [_garmin_activity("4001", sport="cycling")])

    assert counts == {"new": 1, "updated": 0, "skipped": 0}
    # The Garmin canonical now exists and the standalone was absorbed into it.
    assert "4001" in _activity_ids(db)
    assert "intervals_iv9" not in _activity_ids(db)
    # One canonical carrying BOTH links (no duplication).
    assert _links_for(db, "4001") == [("garmin", "4001", "4001"), ("intervals", "iv9", "4001")]
    assert _orphan_count(db) == 0

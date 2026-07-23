"""M1 (#270) §11 шаг 4 — coexistence gates M1-T1 / M1-T2 / M1-T6.

These are END-TO-END coexistence gates through the REAL provider write paths, not
unit-level checks of the normalizer (those are the M0 contract in
test_activity_ingest.py):

- Garmin activities enter through the rewritten persistence path
  ``services.sync._sync_activities`` (the same per-activity common ingest the live
  ``sync_garmin_data`` uses).
- Intervals activities enter through ``services.intervals_sync.sync_intervals_data``
  with a production ``IntervalsICUClient`` whose network layer (``_request_json``)
  is the only thing replaced — the parsing, id validation, normalization and the
  whole windowed-sync + provider-link funnel are the production code.

M0 already proved order-independence, fail-closed non-Garmin attribution and
backfilled-merge at the ingest level. M1's contribution is that BOTH live
provider paths route through that single funnel; these gates lock that contract
end-to-end (contract-lock per slice-spec — no artificial RED phase when the M0
contract already holds).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from data.database import Database
from services.intervals_icu import IntervalsICUClient
from services.intervals_sync import sync_intervals_data
from services.sync import _sync_activities

pytestmark = pytest.mark.smoke

NOW = datetime(2026, 7, 23)


# --- helpers -----------------------------------------------------------------


def _garmin_activity(activity_id: str, *, sport: str = "running", load: float = 47.4) -> dict:
    """A raw Garmin-client activity (pre ActivityProcessor), as _sync_activities consumes."""
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


def _intervals_payload(intervals_id: str, *, external_id: str | None, source: str | None) -> list[dict]:
    """The raw Intervals.icu activities response (one entry)."""
    row = {
        "id": intervals_id,
        "external_id": external_id,
        "source": source,
        "start_date": "2026-07-12T05:00:00Z",
        "start_date_local": "2026-07-12T07:00:00",
        "type": "Ride",
        "name": "Morning Ride",
        "icu_training_load": 60,
        "moving_time": 3600,
    }
    return [row]


class _StubbedClient(IntervalsICUClient):
    """A REAL IntervalsICUClient whose only difference is the network layer:
    ``_request_json`` returns a fixed list. The parsing/id-validation/normalization
    path is production code, so coexistence is exercised through the live funnel.
    """

    def __init__(self, payload):
        super().__init__(api_key="test-key", athlete_id="0")
        self._payload = payload

    def _request_json(self, method, path, payload=None, params=None):
        return self._payload


def _ingest_garmin(db: Database, activity_id: str) -> dict:
    """Run the REAL Garmin persistence path (rewritten in M1-T3) for one activity."""
    warnings: list[str] = []
    counts = _sync_activities(db, [_garmin_activity(activity_id)], warnings=warnings)
    assert not warnings, f"unexpected Garmin warnings: {warnings}"
    return counts


def _ingest_intervals(db: Database, payload: list[dict]) -> object:
    """Run the REAL Intervals sync path (M1-T4) with a stubbed network layer."""
    return sync_intervals_data(db, client=_StubbedClient(payload), now=NOW)


def _snapshot(db: Database) -> dict:
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    activities = [
        dict(row) for row in conn.execute("SELECT activity_id FROM activities ORDER BY activity_id")
    ]
    links = [
        dict(row)
        for row in conn.execute(
            "SELECT canonical_activity_id, provider, provider_activity_id, "
            "external_provider, external_id, match_status "
            "FROM activity_provider_links ORDER BY provider, provider_activity_id"
        )
    ]
    conn.close()
    return {"activities": activities, "links": links}


def _orphan_count(db: Database) -> int:
    conn = sqlite3.connect(db.db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM activity_provider_links l "
        "LEFT JOIN activities a ON a.activity_id = l.canonical_activity_id "
        "WHERE a.activity_id IS NULL"
    ).fetchone()[0]
    conn.close()
    return count


# --- M1-T1: coexistence, both arrival orders ---------------------------------


@pytest.mark.parametrize("order", ["garmin_first", "intervals_first"])
def test_m1_t1_coexistence_one_canonical_two_matched_links(tmp_path, order):
    """Garmin activity G + its Intervals copy (source=GARMIN_CONNECT, external_id=G)
    arrive through the REAL provider paths → ONE canonical activity G, TWO matched
    provider-links (one garmin, one intervals). Independent of arrival order."""
    db = Database(str(tmp_path / f"t1-{order}.db"))
    garmin_id = "555111"
    intervals_payload = _intervals_payload("i_A", external_id=garmin_id, source="GARMIN_CONNECT")

    if order == "garmin_first":
        _ingest_garmin(db, garmin_id)
        _ingest_intervals(db, intervals_payload)
    else:
        _ingest_intervals(db, intervals_payload)
        _ingest_garmin(db, garmin_id)

    snap = _snapshot(db)
    # ONE canonical activity — the Garmin id (primary coordinate)
    assert [a["activity_id"] for a in snap["activities"]] == [garmin_id]
    # TWO links, both matched, on the same canonical
    assert len(snap["links"]) == 2
    assert {link["provider"] for link in snap["links"]} == {"garmin", "intervals"}
    assert all(link["canonical_activity_id"] == garmin_id for link in snap["links"])
    assert all(link["match_status"] == "matched" for link in snap["links"])
    assert _orphan_count(db) == 0


# --- M1-T2: regression — new Garmin activity then Intervals copy joins --------


def test_m1_t2_new_garmin_then_intervals_copy_joins(tmp_path):
    """ExecPlan regression: a NEW Garmin activity synced AFTER M0 through the
    rewritten persistence gets a garmin-link; the Intervals copy then joins the
    SAME canonical (two matched links, one row)."""
    db = Database(str(tmp_path / "t2.db"))
    garmin_id = "555222"

    counts = _ingest_garmin(db, garmin_id)
    assert counts["new"] == 1  # new canonical row created

    snap_after_garmin = _snapshot(db)
    assert [a["activity_id"] for a in snap_after_garmin["activities"]] == [garmin_id]
    assert len(snap_after_garmin["links"]) == 1
    assert snap_after_garmin["links"][0]["provider"] == "garmin"

    _ingest_intervals(db, _intervals_payload("i_B", external_id=garmin_id, source="GARMIN_CONNECT"))

    snap_after_intervals = _snapshot(db)
    # still ONE canonical, now TWO matched links
    assert [a["activity_id"] for a in snap_after_intervals["activities"]] == [garmin_id]
    assert len(snap_after_intervals["links"]) == 2
    assert {link["provider"] for link in snap_after_intervals["links"]} == {"garmin", "intervals"}
    assert all(link["match_status"] == "matched" for link in snap_after_intervals["links"])
    assert _orphan_count(db) == 0


# --- M1-T6: fail-closed end-to-end through real paths ------------------------


def test_m1_t6_non_garmin_source_does_not_merge_with_garmin_history(tmp_path):
    """An Intervals activity whose source is NOT Garmin (e.g. STRAVA) does NOT
    merge with Garmin history even when its external_id numerically matches a
    Garmin id. End-to-end through the real provider paths (M0 proved this at the
    normalizer level; M1-T6 locks it through _sync_activities + sync_intervals_data)."""
    db = Database(str(tmp_path / "t6.db"))
    garmin_id = "555333"

    _ingest_garmin(db, garmin_id)  # Garmin history exists
    _ingest_intervals(
        db,
        _intervals_payload("i_C", external_id=garmin_id, source="STRAVA"),
    )

    snap = _snapshot(db)
    # TWO distinct canonicals — Garmin history intact, Intervals standalone
    ids = {a["activity_id"] for a in snap["activities"]}
    assert ids == {garmin_id, "intervals_i_C"}
    # the Intervals link is standalone (its own canonical), NOT matched to Garmin
    intervals_link = next(link for link in snap["links"] if link["provider"] == "intervals")
    assert intervals_link["canonical_activity_id"] == "intervals_i_C"
    assert intervals_link["match_status"] == "unmatched"
    garmin_link = next(link for link in snap["links"] if link["provider"] == "garmin")
    assert garmin_link["canonical_activity_id"] == garmin_id
    assert _orphan_count(db) == 0


def test_m1_t6_empty_source_does_not_merge_with_garmin_history(tmp_path):
    """A missing/empty source is treated as non-Garmin (fail-closed): the activity
    stays standalone even if external_id matches a Garmin id."""
    db = Database(str(tmp_path / "t6b.db"))
    garmin_id = "555444"

    _ingest_garmin(db, garmin_id)
    _ingest_intervals(db, _intervals_payload("i_D", external_id=garmin_id, source=None))

    snap = _snapshot(db)
    ids = {a["activity_id"] for a in snap["activities"]}
    assert ids == {garmin_id, "intervals_i_D"}
    intervals_link = next(link for link in snap["links"] if link["provider"] == "intervals")
    assert intervals_link["canonical_activity_id"] == "intervals_i_D"
    assert intervals_link["match_status"] == "unmatched"
    assert _orphan_count(db) == 0

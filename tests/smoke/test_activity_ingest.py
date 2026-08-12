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
        "distance": 38000,  # метры (#417)
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


def _created_at(path: str, activity_id: str):
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT created_at FROM activities WHERE activity_id=?", (activity_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


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


def test_normalize_intervals_maps_existing_canonical_summary_fields():
    candidate = normalize_provider_activity(
        _intervals_row(
            elapsed_time=6000,
            moving_time=5700,
            average_heartrate=143.5,
            max_heartrate=181,
            icu_average_watts=226.4,
            icu_weighted_avg_watts=251.2,
            total_elevation_gain=642.7,
            calories=984,
            description="Endurance ride with four steady efforts",
        ),
        "intervals",
    )

    canonical = candidate.canonical
    assert canonical["duration_minutes"] == 100.0
    assert canonical["moving_duration_minutes"] == 95.0
    assert canonical["avg_hr"] == 143.5
    assert canonical["max_hr"] == 181.0
    assert canonical["avg_power"] == 226.4
    assert canonical["elevation_gain"] == 642.7
    assert canonical["calories"] == 984
    assert canonical["description"] == "Endurance ride with four steady efforts"
    # Weighted watts are provider-specific and are not assumed to be normalized
    # power without a separate semantics contract.
    assert canonical.get("normalized_power") is None


def test_normalize_intervals_minimal_payload_keeps_moving_time_fallback():
    candidate = normalize_provider_activity(
        _intervals_row(elapsed_time=None, moving_time=5700),
        "intervals",
    )

    assert candidate.canonical["duration_minutes"] == 95.0
    assert candidate.canonical["moving_duration_minutes"] == 95.0


def test_normalize_intervals_records_utc_not_local_time():
    # blocker #5: local wall clock must not be stored in a *_utc column.
    candidate = normalize_provider_activity(_intervals_row(), "intervals")
    assert candidate.canonical["started_at_utc"] == "2026-07-10T04:30:00Z"
    assert candidate.canonical["date"] == "2026-07-10"  # local date is fine
    # Missing UTC field → None, never the local timestamp.
    no_utc = normalize_provider_activity(_intervals_row(start_date=None), "intervals")
    assert no_utc.canonical["started_at_utc"] is None


def test_normalize_intervals_maps_distance_meters_to_km():
    candidate = normalize_provider_activity(_intervals_row(), "intervals")
    assert candidate.canonical["distance_km"] == 38.0

    no_distance = normalize_provider_activity(
        _intervals_row(distance=None), "intervals"
    )
    assert no_distance.canonical["distance_km"] is None


def test_normalize_intervals_local_first_tss_not_bypassed():
    # blocker #6: a locally-resolved tss is honoured; only a bare row falls back.
    local = normalize_provider_activity(
        _intervals_row(tss=71.5, tss_method="power_tss_bike"), "intervals"
    )
    assert local.canonical["tss"] == 71.5
    assert local.canonical["tss_method"] == "power_tss_bike"
    bare = normalize_provider_activity(_intervals_row(), "intervals")
    assert bare.canonical["tss_method"] == "intervals_icu_provider_fallback"


def test_normalize_intervals_local_first_requires_tss_method_pair():
    # D2 contract (#356): a bare `tss` WITHOUT `tss_method` is not a local result —
    # the pair is the contract, so the row still takes the explicit provider fallback.
    candidate = normalize_provider_activity(
        _intervals_row(tss=71.5), "intervals"
    )
    assert candidate.canonical["tss"] == 90.0
    assert candidate.canonical["tss_method"] == "intervals_icu_provider_fallback"


@pytest.mark.parametrize("source", ["STRAVA", "NOT_GARMIN", "garmin_lite", "", None])
def test_normalize_intervals_only_exact_garmin_source_is_attributed(source):
    # blockers #1/#3: only an exact known-Garmin token attributes external_id to
    # Garmin. A different provider, a look-alike ("NOT_GARMIN" contains "garmin"),
    # or nothing → no coordinate, standalone (never a false Garmin merge).
    candidate = normalize_provider_activity(
        _intervals_row(external_id="555111", source=source), "intervals"
    )
    assert candidate.external_provider is None and candidate.external_id is None
    assert candidate.canonical_activity_id == "intervals_i_777"


@pytest.mark.parametrize("source", ["GARMIN_CONNECT", "GARMIN", "garmin_connect"])
def test_normalize_intervals_known_garmin_tokens_are_attributed(source):
    candidate = normalize_provider_activity(
        _intervals_row(external_id="555111", source=source), "intervals"
    )
    assert (candidate.external_provider, candidate.external_id) == ("garmin", "555111")
    assert candidate.canonical_activity_id == "555111"


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


def test_garmin_primary_projection_is_not_overwritten_by_intervals_summary(tmp_path):
    path = str(tmp_path / "garmin_primary_summary.db")
    db = Database(path)
    intervals = normalize_provider_activity(
        _intervals_row(
            elapsed_time=6300,
            average_heartrate=150,
            max_heartrate=188,
            icu_average_watts=245,
            total_elevation_gain=720,
            calories=1050,
            description="Intervals copy",
        ),
        "intervals",
    )
    garmin = normalize_provider_activity(_garmin_row(), "garmin")

    ingest_provider_activity(db, intervals, primary_source="garmin")
    ingest_provider_activity(db, garmin, primary_source="garmin")

    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT duration_minutes, avg_hr, avg_power, description "
        "FROM activities WHERE activity_id='555111'"
    ).fetchone()
    conn.close()
    assert row == (95.0, 141.0, None, None)


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
    assert links["intervals"]["external_provider"] is None  # not attributed to Garmin
    assert _orphan_count(path) == 0


def _ingest_two_intervals_claimants(path, order):
    db = Database(path)
    a = normalize_provider_activity(_intervals_row(intervals_id="i_A", external_id="555111"), "intervals")
    b = normalize_provider_activity(_intervals_row(intervals_id="i_B", external_id="555111"), "intervals")
    for candidate in order:
        ingest_provider_activity(db, {"i_A": a, "i_B": b}[candidate], primary_source="garmin")
    return _snapshot(path)


def test_ambiguous_both_claimants_flagged_order_independent(tmp_path):
    # blocker #1: two Intervals activities claiming the same Garmin id → NEITHER is
    # confidently matched. Both are flagged 'ambiguous' on their own canonical, and
    # the result does not depend on arrival order (no arbitrary first-arrival winner).
    forward = _ingest_two_intervals_claimants(str(tmp_path / "amb_fwd.db"), ["i_A", "i_B"])
    reverse = _ingest_two_intervals_claimants(str(tmp_path / "amb_rev.db"), ["i_B", "i_A"])
    assert forward == reverse

    by_pid = {link["provider_activity_id"]: link for link in forward["links"]}
    assert by_pid["i_A"]["canonical_activity_id"] == "intervals_i_A"
    assert by_pid["i_B"]["canonical_activity_id"] == "intervals_i_B"
    assert by_pid["i_A"]["match_status"] == "ambiguous"
    assert by_pid["i_B"]["match_status"] == "ambiguous"
    # No claimant silently owns the contested Garmin canonical.
    assert {a["activity_id"] for a in forward["activities"]} == {"intervals_i_A", "intervals_i_B"}
    assert _orphan_count(str(tmp_path / "amb_fwd.db")) == 0


def test_ambiguous_with_real_garmin_leaves_garmin_unmatched(tmp_path):
    # A real Garmin activity plus two Intervals claimants: the Garmin canonical keeps
    # only its own link (unmatched); both Intervals claimants are ambiguous/standalone.
    path = str(tmp_path / "amb_garmin.db")
    db = Database(path)
    ingest_provider_activity(db, normalize_provider_activity(_garmin_row("555111"), "garmin"), primary_source="garmin")
    for pid in ("i_A", "i_B"):
        ingest_provider_activity(
            db, normalize_provider_activity(_intervals_row(intervals_id=pid, external_id="555111"), "intervals"),
            primary_source="garmin",
        )
    links = {link["provider_activity_id"]: link for link in _snapshot(path)["links"]}
    assert links["555111"]["provider"] == "garmin"
    assert links["555111"]["match_status"] == "unmatched"
    assert links["i_A"]["match_status"] == "ambiguous"
    assert links["i_B"]["match_status"] == "ambiguous"
    assert _orphan_count(path) == 0


def test_external_identity_change_reprojects_old_canonical(tmp_path):
    # blocker #2: when the AUTHORITATIVE source leaves a surviving canonical, its
    # fields are re-derived from the remaining link — the departed source's TSS and
    # fields must not linger.
    path = str(tmp_path / "reproject.db")
    db = Database(path)
    # primary=intervals → the shared canonical G1 shows INTERVALS' fields.
    ingest_provider_activity(
        db, normalize_provider_activity(_garmin_row("G1"), "garmin"), primary_source="intervals"
    )
    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id="G1"), "intervals"),
        primary_source="intervals",
    )
    g1 = next(a for a in _snapshot(path)["activities"] if a["activity_id"] == "G1")
    assert g1["tss"] == 90.0  # intervals provider load (authoritative)

    # Intervals re-pairs away to G2 (no Garmin G2). G1 keeps only its Garmin link.
    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id="G2"), "intervals"),
        primary_source="intervals",
    )
    g1 = next(a for a in _snapshot(path)["activities"] if a["activity_id"] == "G1")
    assert g1["tss"] == 86.0  # re-derived from the remaining Garmin link
    assert g1["tss_method"] == "power_np"  # departed Intervals fields gone
    assert _orphan_count(path) == 0


def test_external_identity_change_remerge_does_not_double_count(tmp_path):
    # A merged Intervals copy re-pairs to a DIFFERENT real Garmin activity: its load
    # follows to the new canonical and is not left behind on the old one.
    path = str(tmp_path / "remerge.db")
    db = Database(path)
    for gid in ("G1", "G2"):
        ingest_provider_activity(
            db, normalize_provider_activity(_garmin_row(gid), "garmin"), primary_source="garmin"
        )
    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id="G1"), "intervals"),
        primary_source="garmin",
    )
    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id="G2"), "intervals"),
        primary_source="garmin",
    )
    snap = _snapshot(path)
    assert {a["activity_id"] for a in snap["activities"]} == {"G1", "G2"}
    canonicals = {
        (link["provider"], link["canonical_activity_id"]): link
        for link in snap["links"]
    }
    assert ("intervals", "G2") in canonicals  # moved to G2
    assert ("intervals", "G1") not in canonicals  # not left on G1
    assert canonicals[("garmin", "G1")]["match_status"] == "unmatched"
    assert canonicals[("garmin", "G2")]["match_status"] == "matched"
    assert _orphan_count(path) == 0


def test_backfilled_garmin_activity_merges_with_intervals_copy(tmp_path):
    # Regression gate: an existing (pre-provider-link) Garmin activity → backfill →
    # Intervals copy referencing it → ONE canonical with TWO matched links. The
    # backfilled Garmin link has external_id=NULL, so the resolver must recognise the
    # Garmin activity by its provider_activity_id (else: two activities, doubled load).
    path = str(tmp_path / "backfill_merge.db")
    db = Database(path)
    db.save_activities([
        {"activity_id": "555111", "date": "2026-07-10", "sport": "cycling",
         "source_tss": 86.0, "tss": 86.0, "tss_method": "power_np"},
    ])
    backfill_provider_links(db)
    # Sanity: the backfilled Garmin link indeed has no external identity.
    assert _snapshot(path)["links"][0]["external_id"] is None

    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id="555111"), "intervals"),
        primary_source="garmin",
    )

    snap = _snapshot(path)
    assert {a["activity_id"] for a in snap["activities"]} == {"555111"}  # one canonical, no double
    canonical = snap["activities"][0]
    assert canonical["tss"] == 86.0  # Garmin history preserved via backfill snapshot
    links = {link["provider"]: link for link in snap["links"]}
    assert set(links) == {"garmin", "intervals"}
    assert links["garmin"]["canonical_activity_id"] == "555111"
    assert links["intervals"]["canonical_activity_id"] == "555111"
    assert links["garmin"]["match_status"] == "matched"
    assert links["intervals"]["match_status"] == "matched"
    assert _orphan_count(path) == 0


@pytest.mark.parametrize("primary_source", ["garmin", "intervals"])
def test_backfill_immediately_merges_existing_single_intervals_claimant(
    tmp_path,
    primary_source,
):
    """Repair must remove an already-created Intervals duplicate offline.

    Historical real DBs can have a legacy numeric Garmin row while an earlier
    Intervals ingest already created ``intervals_<id>`` for the same coordinate.
    Waiting for a future provider re-fetch is not a repair: old rows may be outside
    the incremental sync window. Backfill therefore resolves and projects now.
    """
    path = str(tmp_path / f"backfill_existing_{primary_source}.db")
    db = Database(path)
    db.save_activities([_garmin_row("555111")])
    ingest_provider_activity(
        db,
        normalize_provider_activity(
            _intervals_row(external_id="555111", icu_training_load=91),
            "intervals",
        ),
        primary_source=primary_source,
    )
    assert _activity_ids(path) == {"555111", "intervals_i_777"}

    counts = backfill_provider_links(db, primary_source=primary_source)

    assert counts["garmin"] == 1
    assert _activity_ids(path) == {"555111"}
    snap = _snapshot(path)
    links = {link["provider"]: link for link in snap["links"]}
    assert set(links) == {"garmin", "intervals"}
    assert {link["canonical_activity_id"] for link in links.values()} == {"555111"}
    assert {link["match_status"] for link in links.values()} == {"matched"}
    expected_tss = 86.0 if primary_source == "garmin" else 91.0
    assert snap["activities"][0]["tss"] == expected_tss
    assert _orphan_count(path) == 0


def test_backfill_keeps_multiple_intervals_claimants_ambiguous(tmp_path):
    path = str(tmp_path / "backfill_ambiguous.db")
    db = Database(path)
    db.save_activities([_garmin_row("555111")])
    for intervals_id in ("i_a", "i_b"):
        ingest_provider_activity(
            db,
            normalize_provider_activity(
                _intervals_row(intervals_id=intervals_id, external_id="555111"),
                "intervals",
            ),
            primary_source="garmin",
        )

    backfill_provider_links(db, primary_source="garmin")

    snap = _snapshot(path)
    assert _activity_ids(path) == {"555111", "intervals_i_a", "intervals_i_b"}
    by_provider_id = {
        (link["provider"], link["provider_activity_id"]): link
        for link in snap["links"]
    }
    assert by_provider_id[("garmin", "555111")]["match_status"] == "unmatched"
    for intervals_id in ("i_a", "i_b"):
        link = by_provider_id[("intervals", intervals_id)]
        assert link["canonical_activity_id"] == f"intervals_{intervals_id}"
        assert link["match_status"] == "ambiguous"
    assert _orphan_count(path) == 0


def test_backfill_rolls_back_link_and_reconciliation_together(tmp_path, monkeypatch):
    path = str(tmp_path / "backfill_atomic.db")
    db = Database(path)
    db.save_activities([_garmin_row("555111")])
    ingest_provider_activity(
        db,
        normalize_provider_activity(_intervals_row(external_id="555111"), "intervals"),
        primary_source="garmin",
    )
    before = _snapshot(path)

    monkeypatch.setattr(
        db,
        "_project_canonical",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected")),
    )
    with pytest.raises(RuntimeError, match="injected"):
        backfill_provider_links(db, primary_source="garmin")

    assert _snapshot(path) == before
    assert _orphan_count(path) == 0


def test_backfill_after_intervals_ingest_adds_no_spurious_link(tmp_path):
    # RED→GREEN idempotency: a projection-created canonical (`intervals_<id>`) is
    # already covered by its Intervals link, so backfill must NOT misclassify it as
    # `legacy_unknown` and attach a spurious second link.
    path = str(tmp_path / "backfill_after_ingest.db")
    db = Database(path)
    ingest_provider_activity(
        db, normalize_provider_activity(_intervals_row(external_id=None), "intervals"),
        primary_source="garmin",
    )
    links_before = _snapshot(path)["links"]

    counts = backfill_provider_links(db)
    assert counts["legacy_unknown"] == 0
    assert _snapshot(path)["links"] == links_before  # no new link invented
    assert {link["provider"] for link in _snapshot(path)["links"]} == {"intervals"}


def test_repeat_identical_ingest_preserves_created_at(tmp_path):
    # RED→GREEN idempotency: re-projecting identical data must not churn
    # activities.created_at. A pinned sentinel makes the assertion clock-independent —
    # INSERT OR REPLACE would reset it, a plain UPDATE leaves it.
    path = str(tmp_path / "created_at.db")
    db = Database(path)
    candidate = normalize_provider_activity(_garmin_row("555111"), "garmin")
    ingest_provider_activity(db, candidate, primary_source="garmin")

    conn = sqlite3.connect(path)
    conn.execute("UPDATE activities SET created_at='2020-01-01 00:00:00' WHERE activity_id='555111'")
    conn.commit()
    conn.close()

    ingest_provider_activity(db, candidate, primary_source="garmin")  # identical repeat
    assert _created_at(path, "555111") == "2020-01-01 00:00:00"


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


def test_clear_all_data_clears_sync_cursors(tmp_path):
    # M1-T8 (#270): reset must clear sync cursors too, else it wipes the activities but
    # leaves a high-water boundary and the purged history never re-syncs (the next sync
    # would start after an already-deleted date). After reset the cursor is gone, so the
    # next window resolves to the 90-day bootstrap rather than the stale boundary.
    from datetime import datetime, timedelta

    from services.sync_cursor import resolve_window_from_cursor

    path = str(tmp_path / "reset-cursor.db")
    db = Database(path)
    ingest_provider_activity(
        db, normalize_provider_activity(_garmin_row("555111"), "garmin"), primary_source="garmin"
    )
    db.set_sync_cursor("intervals", "activities", "2026-07-23")
    assert db.get_sync_cursor("intervals", "activities") == "2026-07-23"

    db.clear_all_data()

    assert db.get_sync_cursor("intervals", "activities") is None
    now = datetime(2026, 7, 23)
    start, end, bootstrapped = resolve_window_from_cursor(
        db.get_sync_cursor("intervals", "activities"),
        now=now,
        overlap_days=1,
        bootstrap_days=90,
    )
    assert bootstrapped is True
    assert start == now - timedelta(days=90)


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

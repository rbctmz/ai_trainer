"""BDD contract for Issue #176 prospective personal recovery analytics.

Contributor-safe: temporary SQLite only, no provider credentials or network.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import pytest

from data.database import Database


def _canonical_snapshot(
    *,
    confidence: float = 0.8,
    stale: bool = False,
    factor_date: str = "2026-07-14",
) -> dict:
    return {
        "score": 72.0,
        "status": "ready",
        "computed_at": "2026-07-14",
        "as_of_date": "2026-07-14",
        "rule_version": "readiness_snapshot_v2",
        "confidence": confidence,
        "stale": stale,
        "is_provisional": False,
        "source_completeness": 0.8,
        "missing_inputs": ["training_readiness"],
        "factors": [
            {
                "key": "hrv",
                "as_of": factor_date,
                "stale_input": False,
                "score": 80.0,
            },
            {
                "key": "sleep",
                "as_of": factor_date,
                "stale_input": False,
                "score": 65.0,
            },
            {
                "key": "tsb",
                "as_of": "2026-07-14",
                "stale_input": False,
                "score": 60.0,
            },
        ],
        "drivers": [],
        "tsb": {"ctl": 20.0, "atl": 30.0, "tsb": -10.0, "as_of": "2026-07-14"},
        "input_provenance": {"as_of_date": "2026-07-14"},
    }


def _snapshot_row(
    snapshot_id: int,
    observed_at_utc: str,
    *,
    local_date: str = "2026-07-14",
    eligible: bool = True,
    capture_mode: str = "prospective",
) -> dict:
    return {
        "id": snapshot_id,
        "capture_mode": capture_mode,
        "local_date": local_date,
        "athlete_timezone": "Europe/Moscow",
        "observed_at_utc": observed_at_utc,
        "eligibility_status": "eligible" if eligible else "ineligible",
        "eligibility_reasons": [] if eligible else ["low_confidence"],
        "score": 70.0 + snapshot_id,
        "snapshot": _canonical_snapshot(),
    }


def _snapshot_payload(
    *,
    fingerprint: str,
    run_id: str,
    observed_at_utc: str,
) -> dict:
    canonical = _canonical_snapshot()
    return {
        "fingerprint": fingerprint,
        "target_key": "readiness:prospective:2026-07-14",
        "capture_mode": "prospective",
        "local_date": "2026-07-14",
        "athlete_timezone": "Europe/Moscow",
        "observed_at_utc": observed_at_utc,
        "capture_run_id": run_id,
        "rule_version": "readiness_snapshot_v2",
        "score": canonical["score"],
        "status": canonical["status"],
        "confidence": canonical["confidence"],
        "as_of_date": canonical["as_of_date"],
        "is_provisional": canonical["is_provisional"],
        "source_completeness": canonical["source_completeness"],
        "stale": canonical["stale"],
        "eligibility_status": "eligible",
        "eligibility_reasons": [],
        "factors": canonical["factors"],
        "drivers": canonical["drivers"],
        "missing_inputs": canonical["missing_inputs"],
        "tsb": canonical["tsb"],
        "provenance": canonical["input_provenance"],
        "snapshot": canonical,
    }


def _episode(
    index: int,
    *,
    week: int,
    status: str = "eligible",
    capture_mode: str = "prospective",
    rpe_band: str | None = None,
    missing_day: int | None = None,
) -> dict:
    day = 1 + (index % 6)
    deltas = {"d1": -8.0 + index % 4, "d2": -3.0 + index % 3, "d3": 1.0 + index % 2}
    if missing_day is not None:
        deltas[f"d{missing_day}"] = None
    return {
        "id": index + 1,
        "target_key": f"session:s{index}",
        "revision": 1,
        "session_id": f"s{index}",
        "session_date": f"2026-{week:02d}-{day:02d}",
        "iso_week": f"2026-W{week:02d}",
        "capture_mode": capture_mode,
        "status": status,
        "stimulus_family": "endurance",
        "sport": "bike",
        "load_bucket": "moderate",
        "adherence": "exact",
        "rpe_band": rpe_band,
        "outcome": {"readiness_deltas": deltas, "recovered_by_day": 2},
        "exclusion_reasons": [] if status == "eligible" else ["major_deviation"],
        "confounders": {},
    }


def test_readiness_builder_filters_every_source_to_as_of(tmp_path) -> None:
    from services.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "bounded.db"))
    for day, hrv, sleep, resting, training in (
        ("2026-07-13", 35.0, 65.0, 55, 60.0),
        ("2026-07-15", 75.0, 95.0, 42, 95.0),
    ):
        db.sync_hrv_data({day: {"rmssd": hrv, "stress_score": 20.0}})
        db.sync_sleep_data({day: {"total_sleep_minutes": 480, "sleep_score": sleep}})
        db.sync_daily_health({day: {"resting_hr": resting}})
        db.sync_training_status({day: {"training_readiness": training}})

    result = build_readiness_snapshot(
        db,
        as_of=date(2026, 7, 14),
        observed_at_utc=datetime(2026, 7, 14, 6, 0, tzinfo=timezone.utc),
    )

    assert result["as_of_date"] == "2026-07-14"
    assert result["rule_version"] == "readiness_snapshot_v2"
    assert all(
        factor.get("as_of") is None or factor["as_of"] <= "2026-07-14"
        for factor in result["factors"]
    )
    assert result["tsb"]["as_of"] == "2026-07-14"


@pytest.mark.parametrize(
    ("snapshot", "eligible", "reason"),
    [
        (_canonical_snapshot(confidence=0.60), True, None),
        (_canonical_snapshot(confidence=0.59), False, "low_confidence"),
        (_canonical_snapshot(stale=True), False, "stale_snapshot"),
        (_canonical_snapshot(factor_date="2026-07-15"), False, "future_factor"),
    ],
)
def test_snapshot_eligibility_is_pre_registered(
    snapshot: dict,
    eligible: bool,
    reason: str | None,
) -> None:
    from models.recovery_response import evaluate_snapshot_eligibility

    result = evaluate_snapshot_eligibility(snapshot, athlete_timezone="Europe/Moscow")

    assert result["eligible"] is eligible
    if reason:
        assert reason in result["reasons"]
    else:
        assert result["reasons"] == []


def test_invalid_athlete_timezone_fails_closed() -> None:
    from models.recovery_response import evaluate_snapshot_eligibility

    result = evaluate_snapshot_eligibility(
        _canonical_snapshot(), athlete_timezone="Mars/Olympus"
    )

    assert result == {"eligible": False, "reasons": ["invalid_timezone"]}


def test_daily_anchor_uses_latest_snapshot_before_activity_or_noon() -> None:
    from models.recovery_response import select_daily_anchor

    rows = [
        _snapshot_row(1, "2026-07-14T03:30:00Z"),  # 06:30 Moscow
        _snapshot_row(2, "2026-07-14T05:30:00Z"),  # 08:30 Moscow, after activity
    ]
    selected = select_daily_anchor(
        rows,
        [{"date": "2026-07-14", "started_at_utc": "2026-07-14T04:00:00Z"}],
        local_date=date(2026, 7, 14),
        athlete_timezone="Europe/Moscow",
    )

    assert selected["snapshot"]["id"] == 1
    assert selected["reason"] is None
    assert selected["cutoff_at_utc"] == "2026-07-14T04:00:00Z"


def test_daily_anchor_refuses_missing_activity_start() -> None:
    from models.recovery_response import select_daily_anchor

    selected = select_daily_anchor(
        [_snapshot_row(1, "2026-07-14T03:30:00Z")],
        [{"date": "2026-07-14", "started_at_utc": None}],
        local_date=date(2026, 7, 14),
        athlete_timezone="Europe/Moscow",
    )

    assert selected["snapshot"] is None
    assert selected["reason"] == "activity_start_missing"


def test_daily_anchor_without_activity_uses_local_noon() -> None:
    from models.recovery_response import select_daily_anchor

    selected = select_daily_anchor(
        [
            _snapshot_row(1, "2026-07-14T08:59:00Z"),
            _snapshot_row(2, "2026-07-14T09:01:00Z"),
        ],
        [],
        local_date=date(2026, 7, 14),
        athlete_timezone="Europe/Moscow",
    )

    assert selected["snapshot"]["id"] == 1
    assert selected["cutoff_at_utc"] == "2026-07-14T09:00:00Z"


def test_daily_anchor_honors_requested_capture_mode() -> None:
    from models.recovery_response import select_daily_anchor

    prospective = _snapshot_row(1, "2026-07-14T03:30:00Z")
    backfilled = {
        **_snapshot_row(2, "2026-07-14T04:30:00Z"),
        "capture_mode": "backfilled",
    }

    selected = select_daily_anchor(
        [prospective, backfilled],
        [],
        local_date=date(2026, 7, 14),
        athlete_timezone="Europe/Moscow",
        capture_mode="backfilled",
    )

    assert selected["snapshot"]["id"] == 2


def test_snapshot_journal_is_idempotent_and_revisions_are_append_only(tmp_path) -> None:
    db = Database(str(tmp_path / "snapshots.db"))
    first_payload = _snapshot_payload(
        fingerprint="run-a-fingerprint",
        run_id="run-a",
        observed_at_utc="2026-07-14T06:00:00Z",
    )
    first = db.save_readiness_snapshot(first_payload)
    retry = db.save_readiness_snapshot(first_payload)
    second = db.save_readiness_snapshot(
        _snapshot_payload(
            fingerprint="run-b-fingerprint",
            run_id="run-b",
            observed_at_utc="2026-07-14T08:00:00Z",
        )
    )

    assert first["created"] is True
    assert retry["created"] is False
    assert retry["snapshot"]["id"] == first["snapshot"]["id"]
    assert second["snapshot"]["revision"] == 2
    assert second["snapshot"]["supersedes_snapshot_id"] == first["snapshot"]["id"]
    assert len(db.get_readiness_snapshot_history(first_payload["target_key"])) == 2


def test_snapshot_retry_is_atomic_across_two_connections(tmp_path) -> None:
    path = str(tmp_path / "snapshot-race.db")
    Database(path)
    payload = _snapshot_payload(
        fingerprint="same-run",
        run_id="same-run",
        observed_at_utc="2026-07-14T06:00:00Z",
    )

    def save_once() -> int:
        return Database(path).save_readiness_snapshot(payload)["snapshot"]["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _value: save_once(), range(2)))

    assert ids[0] == ids[1]
    assert len(Database(path).get_readiness_snapshot_history(payload["target_key"])) == 1


@pytest.mark.parametrize(
    ("tss", "expected"),
    [(0.1, "low"), (39.9, "low"), (40.0, "moderate"), (79.9, "moderate"), (80.0, "high")],
)
def test_actual_load_buckets_are_frozen(tss: float, expected: str) -> None:
    from models.recovery_response import actual_load_bucket

    assert actual_load_bucket(tss) == expected


@pytest.mark.parametrize(
    ("rpe", "expected"),
    [(None, None), (1, "low"), (3, "low"), (4, "moderate"), (6, "moderate"), (7, "high"), (10, "high")],
)
def test_rpe_bands_are_independent(rpe: int | None, expected: str | None) -> None:
    from models.recovery_response import rpe_band

    assert rpe_band(rpe) == expected


def test_missing_d2_stays_missing_without_erasing_other_outcomes() -> None:
    from models.recovery_response import build_episode_outcomes

    result = build_episode_outcomes(
        pre={"score": 70.0},
        d1={"score": 62.0},
        d2=None,
        d3={"score": 72.0},
    )

    assert result["readiness_deltas"] == {"d1": -8.0, "d2": None, "d3": 2.0}
    assert result["recovered_by_day"] == 3
    assert result["missing_days"] == [2]


@pytest.mark.parametrize(
    ("n", "weeks", "maturity", "publishable"),
    [
        (9, 3, "collection_only", False),
        (10, 3, "early_signal", True),
        (19, 4, "early_signal", True),
        (20, 5, "exploratory", True),
        (29, 7, "exploratory", True),
        (30, 7, "exploratory", True),
        (30, 8, "shadow_pattern", True),
    ],
)
def test_cohort_sample_gates_are_exact(
    n: int,
    weeks: int,
    maturity: str,
    publishable: bool,
) -> None:
    from models.recovery_response import build_recovery_analytics

    episodes = [_episode(index, week=1 + index % weeks) for index in range(n)]
    cohort = build_recovery_analytics(episodes)["registry"][0]

    assert cohort["n"] == n
    assert cohort["distinct_weeks"] == weeks
    assert cohort["maturity"] == maturity
    assert cohort["publishable"] is publishable
    if n < 10:
        assert cohort["points"] == []
    elif n < 20:
        assert all(point["interval"] is None for point in cohort["points"])
    else:
        assert all(point["interval"] is not None for point in cohort["points"])


def test_cluster_bootstrap_is_deterministic_and_preserves_missing_day_counts() -> None:
    from models.recovery_response import build_recovery_analytics

    episodes = [
        _episode(index, week=1 + index % 8, missing_day=2 if index % 4 == 0 else None)
        for index in range(30)
    ]
    first = build_recovery_analytics(episodes)
    second = build_recovery_analytics(list(reversed(episodes)))

    assert first == second
    d2 = next(point for point in first["registry"][0]["points"] if point["day"] == 2)
    assert d2["missing"] == 8
    assert d2["n_observed"] == 22
    assert d2["interval"] is not None


def test_backfill_and_superseded_or_excluded_rows_never_enter_primary_n() -> None:
    from models.recovery_response import build_recovery_analytics

    rows = [_episode(index, week=1 + index % 3) for index in range(10)]
    rows.extend(
        [
            _episode(20, week=1, capture_mode="backfilled"),
            _episode(21, week=1, status="excluded"),
        ]
    )

    result = build_recovery_analytics(rows)

    assert result["registry"][0]["n"] == 10
    assert result["coverage"]["excluded"] == 2
    assert result["coverage"]["backfilled_excluded"] == 1


def test_rpe_overlay_has_an_independent_gate() -> None:
    from models.recovery_response import build_recovery_analytics

    rows = [_episode(index, week=1 + index % 8, rpe_band="high") for index in range(9)]
    rows.extend(
        _episode(index + 20, week=1 + index % 8, rpe_band="moderate")
        for index in range(21)
    )

    overlays = build_recovery_analytics(rows)["registry"][0]["rpe_overlays"]

    assert overlays["high"]["maturity"] == "collection_only"
    assert overlays["high"]["points"] == []
    assert overlays["moderate"]["maturity"] == "exploratory"
    assert overlays["moderate"]["points"]

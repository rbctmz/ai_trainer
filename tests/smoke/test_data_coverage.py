"""Aggregate data-coverage contract for the local sync inventory (#427)."""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.deps import get_database
from api.main import app
from data.database import Database
from services.data_coverage import build_data_coverage


pytestmark = pytest.mark.smoke


def _seed_coverage_rows(db: Database) -> None:
    conn = db._connect()
    conn.executemany(
        "INSERT INTO activities(activity_id, date, sport, activity_name) VALUES (?, ?, ?, ?)",
        [
            ("outside", "2026-07-13", "running", "Outside secret"),
            ("both", "2026-07-14", "cycling", "Private matched ride"),
            ("intervals", "2026-08-12", "running", "Private intervals run"),
            ("unlinked", "2026-08-01", "strength", "Private legacy strength"),
        ],
    )
    conn.executemany(
        """INSERT INTO activity_provider_links(
               canonical_activity_id, provider, provider_activity_id, provider_payload
           ) VALUES (?, ?, ?, ?)""",
        [
            ("outside", "garmin", "g-outside", "outside-provider-secret"),
            ("both", "garmin", "g-both", "garmin-provider-secret"),
            ("both", "intervals", "i-both", "intervals-provider-secret"),
            ("intervals", "intervals", "i-only", "intervals-only-secret"),
        ],
    )
    conn.executemany(
        """INSERT INTO sleep_data(
               date, total_sleep_minutes, total_sleep_source,
               sleep_score, sleep_score_source
           ) VALUES (?, ?, ?, ?, ?)""",
        [
            ("2026-07-14", 12345, "garmin", 91.25, "derived"),
            ("2026-08-12", 54321, "intervals", None, "legacy_unknown"),
        ],
    )
    conn.executemany(
        "INSERT INTO hrv_data(date, rmssd, rmssd_source) VALUES (?, ?, ?)",
        [
            ("2026-07-13", 8888.5, "garmin"),
            ("2026-07-14", 7777.5, "garmin"),
            ("2026-08-11", None, "intervals"),
        ],
    )
    conn.executemany(
        """INSERT INTO daily_health(
               date, resting_hr, resting_hr_source, steps, steps_source
           ) VALUES (?, ?, ?, ?, ?)""",
        [
            ("2026-07-14", 37, "garmin", 0, "garmin"),
            ("2026-08-12", 38, "intervals", 99999, "intervals"),
        ],
    )
    conn.commit()
    conn.close()


def _metric(payload: dict, key: str) -> dict:
    return next(item for item in payload["daily_metrics"] if item["key"] == key)


def test_coverage_uses_inclusive_window_and_keeps_activity_sources_overlapping(tmp_path) -> None:
    db = Database(str(tmp_path / "coverage.db"))
    _seed_coverage_rows(db)

    payload = build_data_coverage(db, days=30, as_of=date(2026, 8, 12))

    assert payload["window"] == {
        "days": 30,
        "start_date": "2026-07-14",
        "end_date": "2026-08-12",
    }
    assert payload["activities"] == {
        "canonical_count": 3,
        "provider_link_counts": {"garmin": 1, "intervals": 2},
        "unattributed_count": 1,
        "latest_date": "2026-08-12",
    }


def test_coverage_counts_only_present_daily_values_and_preserves_zero_steps(tmp_path) -> None:
    db = Database(str(tmp_path / "coverage.db"))
    _seed_coverage_rows(db)

    payload = build_data_coverage(db, days=30, as_of=date(2026, 8, 12))

    assert _metric(payload, "sleep_duration") == {
        "key": "sleep_duration",
        "observed_days": 2,
        "missing_days": 28,
        "coverage_pct": 6.7,
        "latest_date": "2026-08-12",
        "source_days": {"garmin": 1, "intervals": 1},
    }
    assert _metric(payload, "sleep_score")["source_days"] == {"derived": 1}
    assert _metric(payload, "hrv")["observed_days"] == 1
    assert _metric(payload, "hrv")["latest_date"] == "2026-07-14"
    assert _metric(payload, "resting_hr")["observed_days"] == 2
    assert _metric(payload, "steps")["observed_days"] == 2
    assert _metric(payload, "steps")["source_days"] == {"garmin": 1, "intervals": 1}


def test_coverage_empty_database_is_deterministic_and_contains_no_raw_values(tmp_path) -> None:
    db = Database(str(tmp_path / "empty.db"))

    payload = build_data_coverage(db, days=90, as_of=date(2026, 8, 12))

    assert payload["activities"]["canonical_count"] == 0
    assert payload["activities"]["latest_date"] is None
    assert all(metric["observed_days"] == 0 for metric in payload["daily_metrics"])
    assert all(metric["coverage_pct"] == 0.0 for metric in payload["daily_metrics"])


def test_coverage_payload_never_exposes_health_values_names_ids_or_provider_payloads(tmp_path) -> None:
    db = Database(str(tmp_path / "coverage.db"))
    _seed_coverage_rows(db)

    serialized = json.dumps(
        build_data_coverage(db, days=30, as_of=date(2026, 8, 12)),
        sort_keys=True,
    )

    for forbidden in (
        "12345",
        "54321",
        "7777.5",
        "99999",
        "Private matched ride",
        "g-both",
        "provider-secret",
        "provider_payload",
    ):
        assert forbidden not in serialized


@pytest.fixture
def coverage_client(tmp_path):
    db = Database(str(tmp_path / "http.db"))
    _seed_coverage_rows(db)
    app.dependency_overrides[get_database] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_database, None)


@pytest.mark.parametrize("days", [29, 31, 89, 91])
def test_coverage_http_rejects_unsupported_windows(coverage_client, days) -> None:
    response = coverage_client.get("/api/sync/coverage", params={"days": days})
    assert response.status_code == 422


@pytest.mark.parametrize("days", [30, 90])
def test_coverage_http_returns_aggregate_contract_without_provider_io(
    coverage_client,
    monkeypatch: pytest.MonkeyPatch,
    days: int,
) -> None:
    from services import garmin, intervals_icu

    monkeypatch.setattr(garmin, "authenticate", lambda *_a, **_k: pytest.fail("provider I/O"))
    monkeypatch.setattr(intervals_icu, "get_client", lambda: pytest.fail("provider I/O"))

    response = coverage_client.get("/api/sync/coverage", params={"days": days})

    assert response.status_code == 200
    assert response.json()["window"]["days"] == days


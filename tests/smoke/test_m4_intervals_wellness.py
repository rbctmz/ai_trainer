"""M4 contract gates: Intervals wellness → canonical recovery/readiness.

Contributor-safe: temporary SQLite and fake provider transport only. No user
database, API key, Garmin session, or live Intervals request is used.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from data.database import Database
from services.intervals_icu import IntervalsICUClient, IntervalsICUError


class FakeIntervalsClient(IntervalsICUClient):
    def __init__(
        self,
        *,
        activities: Any | None = None,
        wellness: Any | None = None,
        wellness_error: Exception | None = None,
    ) -> None:
        super().__init__(api_key="test-key", athlete_id="0")
        object.__setattr__(self, "_activities", [] if activities is None else activities)
        object.__setattr__(self, "_wellness", [] if wellness is None else wellness)
        object.__setattr__(self, "_wellness_error", wellness_error)
        object.__setattr__(self, "calls", [])

    def _request_json(self, method, path, payload=None, params=None):  # noqa: ANN001
        self.calls.append((method, path, params))
        if path.endswith("/activities"):
            return self._activities
        if path.endswith("/wellness"):
            if self._wellness_error is not None:
                raise self._wellness_error
            return self._wellness
        raise AssertionError(f"unexpected path {path}")


def _wellness_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "2026-07-27",
        "updated": "2026-07-27T06:30:00Z",
        "hrv": 42.5,
        "hrvSDNN": 77.0,
        "sleepSecs": 28_800,
        "sleepScore": 83.0,
        "sleepQuality": 2,
        "restingHR": 51,
        "readiness": 99.0,
        "ctl": 999.0,
        "atl": 888.0,
    }
    row.update(overrides)
    return row


def _normalized_payload(
    *,
    day: str = "2026-07-27",
    source: str,
    rmssd: float,
    sleep_minutes: float,
    sleep_score: float,
    resting_hr: int,
    stages: dict[str, float] | None = None,
) -> dict[str, Any]:
    sleep = {
        "total_sleep_minutes": sleep_minutes,
        "total_sleep_source": source,
        "sleep_score": sleep_score,
        "sleep_score_source": source,
    }
    sleep.update(stages or {})
    return {
        "date": day,
        "hrv": {"rmssd": rmssd, "rmssd_source": source},
        "sleep": sleep,
        "health": {"resting_hr": resting_hr, "resting_hr_source": source},
    }


def test_m4_list_wellness_uses_bounded_fields_and_exact_local_dates():
    client = FakeIntervalsClient(wellness=[_wellness_row()])

    rows = client.list_wellness(date(2026, 7, 1), date(2026, 7, 27))

    assert rows == [_wellness_row()]
    method, path, params = client.calls[-1]
    assert method == "GET"
    assert path == "/api/v1/athlete/0/wellness"
    assert params["oldest"] == "2026-07-01"
    assert params["newest"] == "2026-07-27"
    assert set(params["fields"].split(",")) == {
        "id",
        "updated",
        "restingHR",
        "hrv",
        "hrvSDNN",
        "sleepSecs",
        "sleepScore",
        "sleepQuality",
    }
    assert {"readiness", "ctl", "atl"}.isdisjoint(params["fields"].split(","))


@pytest.mark.parametrize(
    "payload",
    [
        {"id": "2026-07-27"},
        ["not-a-record"],
        [{"hrv": 42}],
        [{"id": "20260727"}],
        [{"id": " 2026-07-27"}],
        [{"id": "2026-02-30"}],
    ],
)
def test_m4_list_wellness_fails_closed_on_malformed_payload(payload):
    client = FakeIntervalsClient(wellness=payload)

    with pytest.raises(IntervalsICUError):
        client.list_wellness(date(2026, 7, 1), date(2026, 7, 27))


def test_m4_mapping_uses_rmssd_and_ignores_provider_models():
    from services.wellness_ingest import normalize_intervals_wellness

    record = normalize_intervals_wellness(_wellness_row())

    assert record.date == "2026-07-27"
    assert record.hrv == {"rmssd": 42.5, "rmssd_source": "intervals"}
    assert record.sleep == {
        "total_sleep_minutes": 480.0,
        "total_sleep_source": "intervals",
        "sleep_score": 83.0,
        "sleep_score_source": "intervals",
    }
    assert record.health == {
        "resting_hr": 51,
        "resting_hr_source": "intervals",
    }
    payload = record.as_payload()
    assert "hrvSDNN" not in str(payload)
    assert "readiness" not in str(payload)
    assert "ctl" not in str(payload)
    assert "atl" not in str(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hrv", "42"),
        ("hrv", float("nan")),
        ("hrv", 0),
        ("sleepSecs", -1),
        ("sleepScore", 101),
        ("restingHR", 19),
        ("restingHR", 250.5),
        ("restingHR", True),
    ],
)
def test_m4_mapping_fails_closed_on_invalid_present_metric(field, value):
    from services.wellness_ingest import normalize_intervals_wellness

    with pytest.raises((TypeError, ValueError)):
        normalize_intervals_wellness(_wellness_row(**{field: value}))


def test_m4_null_metrics_are_absent_not_destructive():
    from services.wellness_ingest import normalize_intervals_wellness

    record = normalize_intervals_wellness(
        _wellness_row(hrv=None, sleepSecs=None, sleepScore=None, restingHR=None)
    )

    assert record.hrv == {}
    assert record.sleep == {}
    assert record.health == {}
    assert record.mapped_metric_count == 0


def test_m4_schema_adds_metric_provenance_without_rewriting_legacy(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE hrv_data (
            date DATE PRIMARY KEY, rmssd REAL, stress_score REAL,
            recovery_score REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE sleep_data (
            date DATE PRIMARY KEY, total_sleep_minutes INTEGER,
            deep_sleep_minutes INTEGER, light_sleep_minutes INTEGER,
            rem_sleep_minutes INTEGER, awakenings_count INTEGER,
            sleep_score REAL, bedtime TEXT, wakeup_time TEXT,
            sleep_efficiency REAL, awake_sleep_minutes REAL,
            sleep_score_source TEXT DEFAULT 'legacy_unknown',
            sleep_efficiency_source TEXT DEFAULT 'legacy_unknown',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE daily_health (
            date DATE PRIMARY KEY, resting_hr INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO hrv_data(date, rmssd) VALUES ('2026-07-26', 40);
        INSERT INTO sleep_data(date, total_sleep_minutes, sleep_score)
            VALUES ('2026-07-26', 420, 70);
        INSERT INTO daily_health(date, resting_hr) VALUES ('2026-07-26', 52);
        """
    )
    conn.commit()
    conn.close()

    Database(str(path))

    conn = sqlite3.connect(path)
    hrv = conn.execute(
        "SELECT rmssd, rmssd_source FROM hrv_data WHERE date='2026-07-26'"
    ).fetchone()
    sleep = conn.execute(
        "SELECT total_sleep_minutes, total_sleep_source, sleep_score_source "
        "FROM sleep_data WHERE date='2026-07-26'"
    ).fetchone()
    health = conn.execute(
        "SELECT resting_hr, resting_hr_source FROM daily_health WHERE date='2026-07-26'"
    ).fetchone()
    conn.close()

    assert hrv == (40.0, "legacy_unknown")
    assert sleep == (420, "legacy_unknown", "legacy_unknown")
    assert health == (52, "legacy_unknown")


def test_m4_wellness_batch_and_cursor_are_atomic(tmp_path):
    db = Database(str(tmp_path / "atomic.db"))
    conn = sqlite3.connect(db.db_path)
    conn.execute(
        """
        CREATE TRIGGER fail_health BEFORE INSERT ON daily_health
        BEGIN SELECT RAISE(ABORT, 'injected health failure'); END
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(sqlite3.IntegrityError):
        db.sync_wellness_batch(
            [
                _normalized_payload(
                    source="intervals",
                    rmssd=42,
                    sleep_minutes=480,
                    sleep_score=83,
                    resting_hr=51,
                )
            ],
            provider="intervals",
            cursor_value="2026-07-27",
            primary_source="intervals",
        )

    conn = sqlite3.connect(db.db_path)
    counts = [
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("hrv_data", "sleep_data", "daily_health")
    ]
    conn.close()
    assert counts == [0, 0, 0]
    assert db.get_sync_cursor("intervals", "wellness") is None


def test_m4_primary_wellness_projection_is_order_independent(tmp_path):
    payload_garmin = _normalized_payload(
        source="garmin",
        rmssd=38,
        sleep_minutes=450,
        sleep_score=76,
        resting_hr=54,
        stages={
            "deep_sleep_minutes": 70,
            "light_sleep_minutes": 300,
            "rem_sleep_minutes": 80,
        },
    )
    payload_intervals = _normalized_payload(
        source="intervals",
        rmssd=44,
        sleep_minutes=485,
        sleep_score=85,
        resting_hr=50,
    )

    snapshots = []
    for name, ordered in (
        ("forward", [("garmin", payload_garmin), ("intervals", payload_intervals)]),
        ("reverse", [("intervals", payload_intervals), ("garmin", payload_garmin)]),
    ):
        db = Database(str(tmp_path / f"{name}.db"))
        for provider, payload in ordered:
            db.sync_wellness_batch(
                [payload],
                provider=provider,
                cursor_value="2026-07-27",
                primary_source="intervals",
            )
        conn = sqlite3.connect(db.db_path)
        snapshots.append(
            {
                "hrv": conn.execute(
                    "SELECT rmssd, rmssd_source FROM hrv_data"
                ).fetchone(),
                "sleep": conn.execute(
                    "SELECT total_sleep_minutes, total_sleep_source, sleep_score, "
                    "sleep_score_source, deep_sleep_minutes, light_sleep_minutes, "
                    "rem_sleep_minutes FROM sleep_data"
                ).fetchone(),
                "health": conn.execute(
                    "SELECT resting_hr, resting_hr_source FROM daily_health"
                ).fetchone(),
            }
        )
        conn.close()

    assert snapshots[0] == snapshots[1]
    assert snapshots[0]["hrv"] == (44.0, "intervals")
    assert snapshots[0]["sleep"] == (
        485,
        "intervals",
        85.0,
        "intervals",
        70,
        300,
        80,
    )
    assert snapshots[0]["health"] == (50, "intervals")


def test_m4_derived_garmin_sleep_score_keeps_provider_priority(
    tmp_path,
    monkeypatch,
):
    """Method provenance (derived) must not erase the owning provider identity."""
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin")
    intervals = _normalized_payload(
        source="intervals",
        rmssd=44,
        sleep_minutes=485,
        sleep_score=85,
        resting_hr=50,
    )
    snapshots = []
    for name, order in (
        ("garmin-first", ("garmin", "intervals")),
        ("intervals-first", ("intervals", "garmin")),
    ):
        db = Database(str(tmp_path / f"{name}.db"))
        for source in order:
            if source == "garmin":
                db.sync_sleep_data(
                    {
                        "2026-07-27": {
                            "total_sleep_minutes": 450,
                            "total_sleep_source": "garmin",
                            "sleep_score": 76,
                            "sleep_score_source": "derived",
                        }
                    }
                )
            else:
                db.sync_wellness_batch(
                    [intervals],
                    provider="intervals",
                    cursor_value="2026-07-27",
                    primary_source="garmin",
                )
        conn = sqlite3.connect(db.db_path)
        snapshots.append(
            conn.execute(
                "SELECT total_sleep_minutes, total_sleep_source, sleep_score, "
                "sleep_score_source FROM sleep_data"
            ).fetchone()
        )
        conn.close()

    assert snapshots == [(450, "garmin", 76.0, "derived")] * 2


def test_m4_intervals_sync_populates_separate_wellness_cursor(tmp_path):
    from services.intervals_sync import sync_intervals_data

    db = Database(str(tmp_path / "vertical.db"))
    client = FakeIntervalsClient(wellness=[_wellness_row()])

    result = sync_intervals_data(
        db,
        client=client,
        now=datetime(2026, 7, 27, 12, 0),
    )

    assert result.halted is False
    assert result.wellness_halted is False
    assert result.recovery_changes == 3
    assert result.wellness_skipped == 0
    assert db.get_sync_cursor("intervals", "activities") == "2026-07-27"
    assert db.get_sync_cursor("intervals", "wellness") == "2026-07-27"
    assert db.get_hrv_data(10_000).iloc[0]["rmssd"] == 42.5
    assert db.get_sleep_data(10_000).iloc[0]["sleep_score_source"] == "intervals"
    assert db.get_daily_health(10_000).iloc[0]["resting_hr_source"] == "intervals"


def test_m4_dirty_wellness_holds_only_wellness_cursor(tmp_path):
    from services.intervals_sync import sync_intervals_data

    db = Database(str(tmp_path / "dirty.db"))
    client = FakeIntervalsClient(wellness=[_wellness_row(hrv="bad")])

    result = sync_intervals_data(
        db,
        client=client,
        now=datetime(2026, 7, 27, 12, 0),
    )

    assert result.halted is False
    assert result.wellness_halted is True
    assert result.warnings
    assert db.get_sync_cursor("intervals", "activities") == "2026-07-27"
    assert db.get_sync_cursor("intervals", "wellness") is None
    assert db.get_hrv_data(10_000).empty


def test_m4_intervals_recovery_is_complete_without_provider_readiness(tmp_path):
    from services.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "readiness.db"))
    db.sync_wellness_batch(
        [
            _normalized_payload(
                source="intervals",
                rmssd=44,
                sleep_minutes=480,
                sleep_score=84,
                resting_hr=50,
            )
        ],
        provider="intervals",
        cursor_value="2026-07-27",
        primary_source="intervals",
    )

    snapshot = build_readiness_snapshot(db, as_of=date(2026, 7, 27))

    assert snapshot["score"] is not None
    assert snapshot["source_completeness"] == 1.0
    assert snapshot["missing_inputs"] == []
    assert snapshot["is_provisional"] is False
    assert snapshot["input_provenance"]["metric_sources"] == {
        "sleep": "intervals",
        "hrv": "intervals",
        "resting_hr": "intervals",
    }
    assert "training_readiness" not in snapshot["missing_inputs"]


def test_m4_duration_only_sleep_reports_the_metric_source_used(tmp_path):
    from services.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "duration-readiness.db"))
    payload = _normalized_payload(
        source="intervals",
        rmssd=44,
        sleep_minutes=480,
        sleep_score=84,
        resting_hr=50,
    )
    payload["sleep"].pop("sleep_score")
    payload["sleep"].pop("sleep_score_source")
    db.sync_wellness_batch(
        [payload],
        provider="intervals",
        cursor_value="2026-07-27",
        primary_source="intervals",
    )

    snapshot = build_readiness_snapshot(db, as_of=date(2026, 7, 27))

    sleep_factor = next(item for item in snapshot["factors"] if item["key"] == "sleep")
    assert sleep_factor["source"] == "total_sleep_minutes"
    assert snapshot["input_provenance"]["metric_sources"]["sleep"] == "intervals"


def test_m4_sleep_and_hrv_api_expose_metric_sources(tmp_path):
    from api.routers.hrv import hrv_summary
    from api.routers.sleep import sleep_summary

    db = Database(str(tmp_path / "api.db"))
    db.sync_wellness_batch(
        [
            _normalized_payload(
                source="intervals",
                rmssd=44,
                sleep_minutes=480,
                sleep_score=84,
                resting_hr=50,
            )
        ],
        provider="intervals",
        cursor_value="2026-07-27",
        primary_source="intervals",
    )

    sleep = sleep_summary(days=10_000, db=db)
    hrv = hrv_summary(days=10_000, db=db)

    assert sleep["latest"]["duration_source"] == "intervals"
    assert sleep["latest"]["score_source"] == "intervals"
    assert sleep["latest"]["stages_available"] is False
    assert sleep["trend"][-1]["duration_source"] == "intervals"
    assert hrv["latest"]["source"] == "intervals"
    assert hrv["baseline"]["source"] == "intervals"
    assert hrv["trend"][-1]["source"] == "intervals"


def test_m4_web_surfaces_are_source_agnostic():
    root = Path(__file__).resolve().parents[2]
    paths = [
        root / "web/app/sleep/page.tsx",
        root / "web/app/hrv/page.tsx",
        root / "web/components/dashboard/SleepWidget.tsx",
        root / "web/components/ui/Tooltip.tsx",
        root / "web/lib/sourceLabels.ts",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "Синхронизируйте Garmin" not in source
    assert 'intervals: "Intervals.icu"' in source
    assert 'from "@/lib/sourceLabels"' in source
    assert "Garmin рассчитывает" not in source
    assert "stages_available" in source

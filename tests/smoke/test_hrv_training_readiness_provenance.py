"""Issue #557 M3 slice 3.3: HRV and training-readiness observation provenance.

Both metrics are stored under the *requested* sync date today, so the row date
cannot prove when they were measured. Provenance comes from the provider: the
Garmin `hrvSummary`/readiness timestamps (converted to the athlete timezone) or
the Intervals.icu wellness `id`, and it moves only with the metric that was
actually accepted.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from data.database import Database


# ------------------------------------------------------------------ Garmin HRV


class _HrvClientStub:
    def __init__(self, summary: dict):
        self._summary = summary

    def get_hrv_data(self, _cdate=None):
        return {"hrvSummary": self._summary}

    def get_stress_data(self, _cdate=None):
        return None

    def get_body_battery_data(self, _cdate=None):
        return None


def _collect_hrv(monkeypatch, summary: dict, day: str = "2026-07-16"):
    from services import sync as sync_module

    monkeypatch.setattr(
        sync_module, "_call_client_method",
        lambda client, method, *args, **kwargs: (getattr(client, method)(*args), None),
    )
    data, _warnings = sync_module._collect_hrv_data(
        _HrvClientStub(summary), [datetime.fromisoformat(day)], None
    )
    return data


def test_hrv_observed_at_uses_local_calendar_date(monkeypatch):
    data = _collect_hrv(
        monkeypatch, {"rmssd": 45.0, "calendarDate": "2026-07-16"}
    )

    assert data["2026-07-16"]["rmssd"] == 45.0
    assert data["2026-07-16"]["rmssd_observed_at"] == "2026-07-16"


def test_hrv_observed_at_converts_gmt_timestamp_to_athlete_local(monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow", raising=False)

    data = _collect_hrv(
        monkeypatch,
        {"rmssd": 45.0, "startTimestampGMT": "2026-07-15T22:30:00.0"},
    )

    # Requested for the 16th, measured late on the 15th UTC -> 16th locally.
    assert data["2026-07-16"]["rmssd_observed_at"] == "2026-07-16"


def test_hrv_observed_at_is_none_without_a_provider_date(monkeypatch):
    data = _collect_hrv(monkeypatch, {"rmssd": 45.0})

    assert data["2026-07-16"]["rmssd_observed_at"] is None


# --------------------------------------------------------------- persistence


def test_hrv_provenance_round_trips_and_survives_a_dateless_resync(tmp_path):
    db = Database(str(tmp_path / "hrv_round_trip.db"))
    db.sync_hrv_data(
        {"2026-07-16": {"rmssd": 45.0, "rmssd_source": "garmin",
                        "rmssd_observed_at": "2026-07-16"}}
    )
    db.sync_hrv_data({"2026-07-17": {"rmssd": 40.0, "rmssd_source": "garmin"}})

    rows = db.get_hrv_data(days=36500).set_index("date")
    assert rows.loc["2026-07-16", "rmssd_observed_at"] == "2026-07-16"
    assert pd.isna(rows.loc["2026-07-17", "rmssd_observed_at"])

    db.sync_hrv_data({"2026-07-16": {"rmssd": 45.0, "rmssd_source": "garmin"}})
    kept = db.get_hrv_data(days=36500).set_index("date")
    assert kept.loc["2026-07-16", "rmssd_observed_at"] == "2026-07-16"


def test_legacy_hrv_table_migrates_and_exposes_null_provenance(tmp_path):
    db_path = tmp_path / "legacy_hrv.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE hrv_data (
            date DATE PRIMARY KEY,
            rmssd REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("INSERT INTO hrv_data (date, rmssd) VALUES ('2026-07-15', 42.0)")
    conn.commit()
    conn.close()

    Database(str(db_path))

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(hrv_data)")}
    row = conn.execute(
        "SELECT rmssd, rmssd_observed_at FROM hrv_data WHERE date='2026-07-15'"
    ).fetchone()
    conn.close()

    assert "rmssd_observed_at" in columns
    assert row == (42.0, None)


def test_rejected_hrv_provider_does_not_change_accepted_provenance(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "hrv_collision.db"))
    db.sync_hrv_data(
        {"2026-07-16": {"rmssd": 45.0, "rmssd_source": "garmin",
                        "rmssd_observed_at": "2026-07-15"}}
    )
    db.sync_hrv_data(
        {"2026-07-16": {"rmssd": 60.0, "rmssd_source": "intervals",
                        "rmssd_observed_at": "2026-07-16"}}
    )

    row = db.get_hrv_data(days=36500).set_index("date").loc["2026-07-16"]
    assert row["rmssd"] == 45.0
    assert row["rmssd_source"] == "garmin"
    assert row["rmssd_observed_at"] == "2026-07-15"


def test_accepted_hrv_updates_value_source_and_provenance_together(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "hrv_accept.db"))
    db.sync_hrv_data(
        {"2026-07-16": {"rmssd": 60.0, "rmssd_source": "intervals",
                        "rmssd_observed_at": "2026-07-16"}}
    )
    db.sync_hrv_data(
        {"2026-07-16": {"rmssd": 45.0, "rmssd_source": "garmin",
                        "rmssd_observed_at": "2026-07-15"}}
    )

    row = db.get_hrv_data(days=36500).set_index("date").loc["2026-07-16"]
    assert row["rmssd"] == 45.0
    assert row["rmssd_source"] == "garmin"
    assert row["rmssd_observed_at"] == "2026-07-15"


def test_intervals_wellness_batch_records_hrv_observation_date(tmp_path):
    from services.wellness_ingest import normalize_intervals_wellness

    db = Database(str(tmp_path / "hrv_intervals.db"))
    record = normalize_intervals_wellness({"id": "2026-07-16", "hrv": 45.0})
    db.sync_wellness_batch(
        [record.as_payload()],
        provider="intervals",
        cursor_value="2026-07-16",
        primary_source="intervals",
        received_at="2026-07-16T06:00:00Z",
    )

    row = db.get_hrv_data(days=36500).set_index("date").loc["2026-07-16"]
    assert row["rmssd"] == 45.0
    assert row["rmssd_source"] == "intervals"
    assert row["rmssd_observed_at"] == "2026-07-16"


def test_intervals_wellness_rejected_hrv_keeps_existing_provenance(tmp_path, monkeypatch):
    from config.settings import Settings

    from services.wellness_ingest import normalize_intervals_wellness

    monkeypatch.setattr(Settings, "PRIMARY_WELLNESS_SOURCE", "garmin", raising=False)

    db = Database(str(tmp_path / "hrv_intervals_rejected.db"))
    db.sync_hrv_data(
        {"2026-07-16": {"rmssd": 45.0, "rmssd_source": "garmin",
                        "rmssd_observed_at": "2026-07-15"}}
    )
    record = normalize_intervals_wellness({"id": "2026-07-16", "hrv": 60.0})
    db.sync_wellness_batch(
        [record.as_payload()],
        provider="intervals",
        cursor_value="2026-07-16",
        primary_source="garmin",
        received_at="2026-07-16T06:00:00Z",
    )

    row = db.get_hrv_data(days=36500).set_index("date").loc["2026-07-16"]
    assert row["rmssd"] == 45.0
    assert row["rmssd_source"] == "garmin"
    assert row["rmssd_observed_at"] == "2026-07-15"


def test_changed_undated_hrv_clears_inherited_provenance(tmp_path):
    """Review P1: provenance must not survive a value change (fail closed)."""
    db = Database(str(tmp_path / "hrv_inherit.db"))
    db.sync_hrv_data(
        {"2026-07-16": {"rmssd": 45.0, "rmssd_source": "garmin",
                        "rmssd_observed_at": "2026-07-16"}}
    )

    # A new, undated measurement replaces the value: the old date is no longer
    # evidence for it.
    db.sync_hrv_data({"2026-07-16": {"rmssd": 70.0, "rmssd_source": "garmin"}})
    changed = db.get_hrv_data(days=36500).set_index("date").loc["2026-07-16"]
    assert changed["rmssd"] == 70.0
    assert pd.isna(changed["rmssd_observed_at"])

    from api.readiness_snapshot import build_readiness_snapshot

    snapshot = build_readiness_snapshot(
        db,
        as_of=date(2026, 7, 16),
        observed_at_utc=datetime(2026, 7, 16, 6, 0, tzinfo=timezone.utc),
    )
    assert snapshot["freshness"]["confirmed_today"] == []
    assert snapshot["freshness"]["unverified"] == ["hrv"]
    assert snapshot["eligible_inputs"] == []

    # An unchanged undated re-sync may keep the known date.
    db.sync_hrv_data(
        {"2026-07-16": {"rmssd": 70.0, "rmssd_source": "garmin",
                        "rmssd_observed_at": "2026-07-16"}}
    )
    db.sync_hrv_data({"2026-07-16": {"rmssd": 70.0, "rmssd_source": "garmin"}})
    kept = db.get_hrv_data(days=36500).set_index("date").loc["2026-07-16"]
    assert kept["rmssd_observed_at"] == "2026-07-16"


# ---------------------------------------------------------- training readiness


class _TrainingClientStub:
    def __init__(self, readiness):
        self._readiness = readiness

    def get_training_status(self):
        return {
            "mostRecentTrainingStatus": {
                "latestTrainingStatusData": {
                    "dev-1": {"trainingStatusFeedbackPhrase": "PRODUCTIVE_1",
                              "recoveryTimeHours": 14}
                }
            }
        }

    def get_vo2_max(self):
        return None

    def get_training_readiness(self):
        return self._readiness


def _collect_training_status(monkeypatch, readiness):
    from services import sync as sync_module

    monkeypatch.setattr(
        sync_module, "_call_client_method",
        lambda client, method, *args, **kwargs: (getattr(client, method)(), None),
    )
    data, _warnings = sync_module._collect_training_status_data(_TrainingClientStub(readiness))
    return data


def test_training_readiness_row_is_dated_by_the_sync_day_and_keeps_payload_provenance(
    monkeypatch,
):
    """The composite status row belongs to the sync day (review P1)."""
    from utils.athlete_time import athlete_local_date

    data = _collect_training_status(
        monkeypatch, {"readinessScore": 78, "calendarDate": "2026-07-16"}
    )

    sync_day = athlete_local_date().isoformat()
    assert list(data) == [sync_day]
    entry = data[sync_day]
    assert entry["training_readiness"] == 78
    # Readiness keeps its own provider date, which is what gates the factor.
    assert entry["training_readiness_observed_at"] == "2026-07-16"


def test_training_readiness_without_a_payload_date_is_unverified(monkeypatch):
    data = _collect_training_status(monkeypatch, {"readinessScore": 66})

    assert len(data) == 1
    entry = next(iter(data.values()))
    assert entry["training_readiness"] == 66
    # The processor strips empty values, so "no date" may be absent or None;
    # both mean unknown provenance for the persistence layer.
    assert entry.get("training_readiness_observed_at") is None


def test_changed_undated_training_readiness_clears_inherited_provenance(tmp_path):
    """Review P1: the same fail-closed rule for device readiness."""
    db = Database(str(tmp_path / "training_inherit.db"))
    db.sync_training_status(
        {"2026-07-16": {"training_readiness": 78.0,
                        "training_readiness_observed_at": "2026-07-16"}}
    )

    db.sync_training_status({"2026-07-16": {"training_readiness": 20.0}})
    changed = db.get_training_status_history(days=36500).set_index("date").loc["2026-07-16"]
    assert changed["training_readiness"] == 20.0
    assert pd.isna(changed["training_readiness_observed_at"])

    # Unchanged value without a date keeps the known provenance.
    db.sync_training_status(
        {"2026-07-16": {"training_readiness": 20.0,
                        "training_readiness_observed_at": "2026-07-16"}}
    )
    db.sync_training_status({"2026-07-16": {"training_readiness": 20.0}})
    kept = db.get_training_status_history(days=36500).set_index("date").loc["2026-07-16"]
    assert kept["training_readiness_observed_at"] == "2026-07-16"


def test_readiness_only_payload_is_not_dropped(monkeypatch):
    """Review P2: a valid readiness payload without training status/VO2 must survive."""
    from services import sync as sync_module

    class _ReadinessOnlyStub:
        def get_training_status(self):
            return None

        def get_vo2_max(self):
            return None

        def get_training_readiness(self):
            return {"readinessScore": 78, "calendarDate": "2026-07-16"}

    monkeypatch.setattr(
        sync_module, "_call_client_method",
        lambda client, method, *args, **kwargs: (getattr(client, method)(), None),
    )
    data, warnings = sync_module._collect_training_status_data(_ReadinessOnlyStub())

    from utils.athlete_time import athlete_local_date

    sync_day = athlete_local_date().isoformat()
    assert list(data) == [sync_day]
    assert data[sync_day]["training_readiness"] == 78
    assert data[sync_day]["training_readiness_observed_at"] == "2026-07-16"
    assert warnings == []


def test_stale_readiness_does_not_move_the_composite_training_row(monkeypatch):
    """Review P1: the composite status row belongs to the sync date, not to readiness."""
    from services import sync as sync_module
    from utils.athlete_time import athlete_local_date

    class _StaleReadinessStub:
        def get_training_status(self):
            return {
                "mostRecentTrainingStatus": {
                    "latestTrainingStatusData": {
                        "dev-1": {"trainingStatusFeedbackPhrase": "PRODUCTIVE_1"}
                    }
                }
            }

        def get_vo2_max(self):
            return {"vo2MaxValue": 52.0, "fitnessAge": 31}

        def get_training_readiness(self):
            yesterday = (athlete_local_date() - timedelta(days=1)).isoformat()
            return {"readinessScore": 78, "calendarDate": yesterday}

    monkeypatch.setattr(
        sync_module, "_call_client_method",
        lambda client, method, *args, **kwargs: (getattr(client, method)(), None),
    )
    data, _warnings = sync_module._collect_training_status_data(_StaleReadinessStub())

    today = athlete_local_date().isoformat()
    yesterday = (athlete_local_date() - timedelta(days=1)).isoformat()
    assert list(data) == [today], "the composite row must stay on the sync date"
    entry = data[today]
    assert entry["vo2_max"] == 52.0
    assert entry["training_readiness"] == 78
    # Readiness keeps its own observation date, so the factor is gated honestly.
    assert entry["training_readiness_observed_at"] == yesterday


def test_training_status_provenance_round_trips_and_survives_a_dateless_resync(tmp_path):
    db = Database(str(tmp_path / "training_round_trip.db"))
    db.sync_training_status(
        {"2026-07-16": {"training_readiness": 78.0,
                        "training_readiness_observed_at": "2026-07-16"}}
    )
    db.sync_training_status({"2026-07-17": {"training_readiness": 70.0}})

    rows = db.get_training_status_history(days=36500).set_index("date")
    assert rows.loc["2026-07-16", "training_readiness_observed_at"] == "2026-07-16"
    assert pd.isna(rows.loc["2026-07-17", "training_readiness_observed_at"])

    db.sync_training_status({"2026-07-16": {"training_readiness": 78.0}})
    kept = db.get_training_status_history(days=36500).set_index("date")
    assert kept.loc["2026-07-16", "training_readiness_observed_at"] == "2026-07-16"


def test_legacy_training_status_table_migrates_with_null_provenance(tmp_path):
    db_path = tmp_path / "legacy_training.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE training_status (
            date DATE PRIMARY KEY,
            training_readiness REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO training_status (date, training_readiness) VALUES ('2026-07-15', 66.0)"
    )
    conn.commit()
    conn.close()

    Database(str(db_path))

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(training_status)")}
    row = conn.execute(
        "SELECT training_readiness, training_readiness_observed_at "
        "FROM training_status WHERE date='2026-07-15'"
    ).fetchone()
    conn.close()

    assert "training_readiness_observed_at" in columns
    assert row == (66.0, None)


# ---------------------------------------------------------------- eligibility


def test_dated_training_readiness_counts_but_cannot_open_the_gate(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "training_snapshot.db"))
    db.sync_training_status(
        {"2026-07-16": {"training_readiness": 78.0,
                        "training_readiness_observed_at": "2026-07-16"}}
    )
    snapshot = build_readiness_snapshot(
        db,
        as_of=date(2026, 7, 16),
        observed_at_utc=datetime(2026, 7, 16, 6, 0, tzinfo=timezone.utc),
    )

    assert snapshot["freshness"]["confirmed_today"] == ["training_readiness"]
    assert "training_readiness" in snapshot["eligible_inputs"]
    assert snapshot["intervention_confidence"] == 0.2
    # Device readiness is not a primary recovery measurement.
    assert snapshot["intervention_score"] is None
    assert (
        snapshot["intervention_blocked_reason"]
        == "no_confirmed_today_primary_recovery_measurement"
    )

    dateless = Database(str(tmp_path / "training_dateless.db"))
    dateless.sync_training_status({"2026-07-16": {"training_readiness": 78.0}})
    undated = build_readiness_snapshot(
        dateless,
        as_of=date(2026, 7, 16),
        observed_at_utc=datetime(2026, 7, 16, 6, 0, tzinfo=timezone.utc),
    )
    assert undated["freshness"]["confirmed_today"] == []
    assert undated["freshness"]["unverified"] == ["training_readiness"]
    assert undated["eligible_inputs"] == []


def test_hrv_provenance_reaches_the_snapshot(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "hrv_snapshot.db"))
    db.sync_hrv_data(
        {"2026-07-16": {"rmssd": 45.0, "rmssd_source": "garmin",
                        "rmssd_observed_at": "2026-07-16"}}
    )
    snapshot = build_readiness_snapshot(
        db,
        as_of=date(2026, 7, 16),
        observed_at_utc=datetime(2026, 7, 16, 6, 0, tzinfo=timezone.utc),
    )

    assert snapshot["freshness"]["confirmed_today"] == ["hrv"]
    assert "hrv" in snapshot["eligible_inputs"]
    assert snapshot["intervention_score"] is not None

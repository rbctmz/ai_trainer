"""Operator-safe provider-link reconciliation CLI contract (#429)."""
from __future__ import annotations

import json
import sqlite3

import pytest

from data.database import Database
from scripts.backfill_activity_provider_links import repair_database
from services.activity_ingest import ingest_provider_activity, normalize_provider_activity


pytestmark = pytest.mark.smoke


def _seed(db: Database) -> None:
    db.save_activities(
        [
            {"activity_id": "111", "date": "2026-07-01", "sport": "running", "tss": 40},
            {"activity_id": "legacy_x", "date": "2026-07-02", "sport": "gym", "tss": 20},
        ]
    )
    ingest_provider_activity(
        db,
        normalize_provider_activity(
            {
                "id": "i_111",
                "external_id": "111",
                "source": "GARMIN_CONNECT",
                "start_date": "2026-07-01T06:00:00Z",
                "type": "Run",
                "icu_training_load": 41,
                "moving_time": 1800,
            },
            "intervals",
        ),
        primary_source="garmin",
    )


def _counts(path: str) -> tuple[int, int]:
    with sqlite3.connect(path) as conn:
        return (
            conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM activity_provider_links").fetchone()[0],
        )


def test_dry_run_is_read_only_and_returns_aggregate_evidence_only(tmp_path) -> None:
    path = str(tmp_path / "dry_run.db")
    db = Database(path)
    _seed(db)
    before = _counts(path)

    result = repair_database(path, apply=False, primary_source="garmin")

    assert result == {
        "mode": "dry-run",
        "database": path,
        "before": {
            "unlinked_total": 2,
            "classifications": {"garmin": 1, "legacy_unknown": 1},
            "garmin_coordinates": {"matched": 1, "standalone": 0, "ambiguous": 0},
        },
    }
    assert _counts(path) == before
    serialized = json.dumps(result)
    assert "111" not in serialized
    assert "legacy_x" not in serialized
    assert "i_111" not in serialized


def test_apply_reconciles_then_second_run_is_idempotent(tmp_path) -> None:
    path = str(tmp_path / "apply.db")
    db = Database(path)
    _seed(db)

    first = repair_database(path, apply=True, primary_source="garmin")
    second = repair_database(path, apply=True, primary_source="garmin")

    assert first["mode"] == "apply"
    assert first["applied"]["garmin"] == 1
    assert first["applied"]["legacy_unknown"] == 1
    assert first["after"]["unlinked_total"] == 0
    assert second["applied"] == {
        "garmin": 0,
        "demo": 0,
        "legacy_unknown": 0,
        "skipped_existing": 2,
    }
    with sqlite3.connect(path) as conn:
        activities = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        matched = conn.execute(
            "SELECT COUNT(*) FROM activity_provider_links WHERE match_status='matched'"
        ).fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    assert activities == 2
    assert matched == 2
    assert integrity == "ok"


def test_repair_rejects_missing_database_and_invalid_primary(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        repair_database(tmp_path / "missing.db", apply=False, primary_source="garmin")

    path = tmp_path / "exists.db"
    Database(str(path))
    with pytest.raises(ValueError, match="primary_source"):
        repair_database(path, apply=False, primary_source="unknown")

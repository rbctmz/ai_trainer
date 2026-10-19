"""M2 storage lifecycle on synthetic temporary SQLite; no application confirm."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from api import planning_service as ps
from config.settings import Settings, _positive_int_env
from data.database import Database
from data.planning_build_preview_store import get_preview, store_pending, validate_pending
from models.planning_build_confirmation import BuildParameters, PlanningBuildPreviewError, canonical_json
from scripts.sqlite_backup_restore import backup_database, restore_database
from tests.smoke._planning_build_confirmation import cycle_fields, parameters, pin_clock, protected_state, seeded_db
from tests.smoke.test_planning_build_preparation import execute, pending_count

NOW = datetime(2026, 10, 16, 9, tzinfo=timezone.utc)


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    pin_clock(monkeypatch)
    db = seeded_db(tmp_path)
    snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping({**parameters(), **cycle_fields(db)}))
    prepared = ps._calculate_plan_build(snapshot)
    return db, prepared


def retain(db, prepared, *, now=NOW):
    return store_pending(db, prepared, origin="planning_ui", now=now,
                         recheck=lambda _conn: prepared.snapshot.dependency_digest)


def test_pending_survives_reopen_idempotent_init_and_safe_read(artifact):
    db, prepared = artifact
    before = protected_state(db)
    row = retain(db, prepared)
    reopened = Database(db.db_path)
    reopened.init_tables()
    restored = get_preview(reopened, row["preview_id"], origin="planning_ui")
    assert restored["payload_digest"] == row["payload_digest"]
    assert restored["checkpoint_json"] == prepared.checkpoint_json
    assert restored["response_json"] == prepared.response_json
    assert restored["coach_proposal_id"] is restored["applied_checkpoint_id"] is None
    assert protected_state(db) == before
    # Returned copies cannot mutate retained data.
    restored["checkpoint_json"] = "changed"
    assert get_preview(db, row["preview_id"], origin="planning_ui")["checkpoint_json"] == prepared.checkpoint_json


def test_owner_namespace_and_origin_cannot_import_another_preview(artifact, tmp_path):
    db, prepared = artifact
    row = retain(db, prepared)
    other = Database(str(tmp_path / "other.db"))
    for database, origin in ((db, "coach"), (other, "planning_ui")):
        with pytest.raises(PlanningBuildPreviewError) as error:
            get_preview(database, row["preview_id"], origin=origin)
        assert error.value.code == "preview_not_found"
        assert error.value.status == 404
    assert pending_count(db) == 1
    assert pending_count(other) == 0


@pytest.mark.parametrize("delta,valid", [(-1, True), (0, False), (1, False)])
def test_expiry_is_inclusive_and_read_does_not_cleanup(artifact, delta, valid):
    db, prepared = artifact
    row = retain(db, prepared)
    expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    now = expiry + timedelta(microseconds=delta)
    retained = get_preview(db, row["preview_id"], origin="planning_ui")
    if valid:
        validate_pending(retained, now=now)
    else:
        with pytest.raises(PlanningBuildPreviewError) as error:
            validate_pending(retained, now=now)
        assert error.value.code == "preview_expired"
        assert error.value.status == 410
    assert pending_count(db) == 1


@pytest.mark.parametrize("column,value", [
    ("checkpoint_json", "{broken"), ("response_json", "{}"),
    ("parameters_json", "[]"), ("settings_write_json", "changed"),
    ("schema_version", 999), ("dependency_digest", "changed"),
])
def test_corruption_fails_closed_without_repair_or_active_mutation(artifact, column, value):
    db, prepared = artifact
    row = retain(db, prepared)
    before = protected_state(db)
    # Column names are fixed by this test's closed parameter list.
    execute(db, f"UPDATE planning_build_previews SET {column} = ? WHERE preview_id = ?", (value, row["preview_id"]))
    with pytest.raises(PlanningBuildPreviewError) as error:
        get_preview(db, row["preview_id"], origin="planning_ui")
    assert error.value.code == "preview_corrupt"
    assert error.value.status == 500
    assert pending_count(db) == 1
    assert protected_state(db) == before


@pytest.mark.parametrize("payload", ["[]", "{broken", '{"invalid":NaN}'])
def test_invalid_serialized_result_is_rejected_before_insert(artifact, payload):
    db, prepared = artifact
    before = protected_state(db)
    with pytest.raises(ValueError):
        retain(db, replace(prepared, response_json=payload))
    assert pending_count(db) == 0
    assert protected_state(db) == before


def test_freshness_failure_rolls_back_pending_insertion(artifact):
    db, prepared = artifact
    before = protected_state(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        store_pending(db, prepared, origin="planning_ui", now=NOW, recheck=lambda _conn: "stale")
    assert error.value.code == "preview_stale"
    assert pending_count(db) == 0
    assert protected_state(db) == before


def test_cleanup_is_bounded_and_never_deletes_applied_state(artifact, monkeypatch):
    db, prepared = artifact
    monkeypatch.setattr(Settings, "PLANNING_BUILD_PREVIEW_RETENTION_DAYS", 7)
    old = NOW - timedelta(days=10)
    rows = [retain(db, prepared, now=old) for _ in range(105)]
    # M2 has no apply operation. Seed only the future receipt STORAGE SHAPE to
    # exercise cleanup; this does not claim M3 receipt/replay verification.
    execute(db, "UPDATE planning_build_previews SET state='applied',applied_checkpoint_id=999,"
                "applied_at=?,applied_response_json='{}',receipt_digest='synthetic' WHERE preview_id=?",
            (rows[0]["created_at"], rows[0]["preview_id"]))
    execute(db, "UPDATE planning_build_previews SET state='invalidated' WHERE preview_id=?", (rows[1]["preview_id"],))
    retain(db, prepared)
    assert pending_count(db) == 6  # 105 old - 100 bounded cleanup + 1 new
    retain(db, prepared)
    assert pending_count(db) == 3  # applied + two new; remaining four old rows removed
    conn = db._connect()
    try:
        assert conn.execute("SELECT state FROM planning_build_previews WHERE preview_id=?",
                            (rows[0]["preview_id"],)).fetchone() == ("applied",)
    finally:
        conn.close()


def test_reset_removes_preview_rows_idempotently(artifact):
    db, prepared = artifact
    retain(db, prepared)
    db.clear_all_data()
    db.clear_all_data()
    reopened = Database(db.db_path)
    assert pending_count(reopened) == 0
    assert reopened.get_latest_planning_checkpoint() is None
    assert protected_state(reopened)["settings"] == []


def test_backup_restore_retains_artifact_and_reset_does_not_reappear(artifact, tmp_path):
    db, prepared = artifact
    row = retain(db, prepared)
    backup = tmp_path / "preview-backup.sqlite"
    target = tmp_path / "preview-restored.sqlite"
    backup_database(db.db_path, backup, confirm_stopped=True)
    restore_database(backup, target, confirm_stopped=True)
    restored = Database(str(target))
    assert get_preview(restored, row["preview_id"], origin="planning_ui")["payload_digest"] == row["payload_digest"]
    restored.clear_all_data()
    assert pending_count(Database(str(target))) == 0


def test_failed_insert_rolls_back_cleanup_as_well(artifact):
    db, prepared = artifact
    row = retain(db, prepared, now=NOW - timedelta(days=10))
    execute(db, "CREATE TRIGGER synthetic_preview_failure BEFORE INSERT ON planning_build_previews "
                "BEGIN SELECT RAISE(ABORT, 'synthetic storage failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic storage failure"):
        retain(db, prepared)
    assert pending_count(db) == 1  # cleanup was rolled back too
    assert get_preview(db, row["preview_id"], origin="planning_ui")["state"] == "pending"


def test_configuration_affects_new_expiry_only(artifact, monkeypatch):
    db, prepared = artifact
    monkeypatch.setattr(Settings, "PLANNING_BUILD_PREVIEW_TTL_SECONDS", 1800)
    original = retain(db, prepared)
    monkeypatch.setattr(Settings, "PLANNING_BUILD_PREVIEW_TTL_SECONDS", 60)
    newer = retain(db, prepared)
    assert original["expires_at"] != newer["expires_at"]
    assert get_preview(db, original["preview_id"], origin="planning_ui")["expires_at"] == original["expires_at"]


@pytest.mark.parametrize("value", ["0", "-1", "bad", "1.5"])
def test_configuration_requires_positive_integer(monkeypatch, value):
    monkeypatch.setenv("PLANNING_BUILD_PREVIEW_TTL_SECONDS", value)
    with pytest.raises(ValueError):
        _positive_int_env("PLANNING_BUILD_PREVIEW_TTL_SECONDS", 1800)


def test_retained_context_has_component_hashes_not_copied_activity_history(artifact):
    db, prepared = artifact
    row = retain(db, prepared)
    context = json.loads(row["dependency_context_json"])
    assert set(context["components"]) == {"activities", "athlete_profile", "constraints", "constraint_ownership", "latest_checkpoint", "settings"}
    assert all(len(value) == 64 for value in context["components"].values())
    assert "sources_json" not in row
    assert canonical_json(context) == row["dependency_context_json"]

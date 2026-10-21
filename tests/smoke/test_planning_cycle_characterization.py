"""Green byte-preservation boundary, independent of not-yet-built S2 routes."""
import json

import pytest

from api import planning_service as ps
from data.database import Database
from data.planning_build_preview_store import get_preview
from models.planning_build_confirmation import BuildParameters
from models.planning_checkpoints import build_planning_checkpoint
from scripts.sqlite_backup_restore import backup_database, restore_database
from tests.smoke._planning_build_confirmation import cycle_fields, declared_entry_limits, ready_parameters as parameters
from tests.smoke._planning_cycle_regressions import (
    client_for, evidence_bytes, first_session_id, legacy_db, plan, seed_evidence,
)

pytestmark = pytest.mark.smoke


def test_characterization_full_history_and_ledgers_survive_reads_and_restart(tmp_path, monkeypatch):
    payload = build_planning_checkpoint(plan())
    # Deliberately noncanonical whitespace: migrating/reserializing old JSON is
    # forbidden even if the parsed values would compare equal.
    raw = json.dumps(payload, ensure_ascii=False, indent=3)
    db = legacy_db(tmp_path, monkeypatch, payloads=[raw, raw])
    sid = first_session_id(plan())
    match, feedback, delivery = seed_evidence(db, sid)
    before = evidence_bytes(db)
    with client_for(db) as client:
        for path in ("status", "overview", "edit-context", "history", "plan"):
            response = client.get(f"/api/planning/{path}")
            assert response.status_code == 200, (path, response.text)
    reopened = Database(str(tmp_path / "plan.db"))
    assert evidence_bytes(reopened) == before
    assert reopened.get_planning_checkpoint(1)["id"] == 1
    assert reopened.get_planning_checkpoint(2)["id"] == 2
    assert reopened.get_latest_plan_actual_match_for_session(sid)["id"] == match["id"]
    assert reopened.get_latest_session_feedback(sid)["id"] == feedback["id"]
    assert reopened.get_intervals_plan_deliveries()[0]["id"] == delivery["id"]


def test_characterization_s1_preview_is_not_an_active_write(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    seed_evidence(db, first_session_id(plan()))
    before = evidence_bytes(db)
    result = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping({**parameters(), **cycle_fields(db), "initial_dose_limits": declared_entry_limits()}),
                                   origin="planning_ui")
    preview_id = result["confirmation"]["preview_id"]
    retained = get_preview(db, preview_id, origin="planning_ui")
    assert retained["checkpoint_json"]
    # Abandoning a preview is cancellation; it is not a checkpoint mutation.
    assert evidence_bytes(db) == before
    assert evidence_bytes(Database(str(tmp_path / "plan.db"))) == before


def test_characterization_backup_api_preserves_history_and_ledgers(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    seed_evidence(db, first_session_id(plan()))
    before = evidence_bytes(db)
    backup = tmp_path / "snapshot.db"
    restored = tmp_path / "restored.db"
    backup_database(db.db_path, backup, confirm_stopped=True)
    restore_database(backup, restored, confirm_stopped=True)
    assert evidence_bytes(Database(str(restored))) == before

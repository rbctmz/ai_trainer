"""M3: exact publication, transactional rollback and durable replay on synthetic SQLite."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import sqlite3
from threading import Barrier, Event
from uuid import uuid4

import pytest

from api import planning_service as ps
from config.settings import Settings
from data.database import Database
from data.planning_build_preview_store import get_preview
from models import planning_build_confirmation as protocol
from models.planning_build_confirmation import BuildParameters, PlanningBuildPreviewError
from tests.smoke._planning_build_confirmation import (
    MODES, TODAY, add_late_activity, checkpoint_payload, parameters, pin_clock, protected_state, seeded_db,
)
from tests.smoke.test_planning_build_preparation import execute


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    pin_clock(monkeypatch)


def prepare(db, mode="training_goal", origin="planning_ui"):
    return ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(parameters(mode)), origin=origin)


def confirm(db, shown):
    return ps.confirm_plan_build(db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui")


def error_code(db, shown, code):
    with pytest.raises(PlanningBuildPreviewError) as error:
        confirm(db, shown)
    assert error.value.code == code
    return error.value


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("existing", [False, True])
def test_commit_is_complete_frozen_payload_without_calculation(tmp_path, monkeypatch, mode, existing):
    db = seeded_db(tmp_path, existing=existing, rested=True)
    shown = prepare(db, mode)
    row = get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui")
    before = protected_state(db)

    def forbidden(*args, **kwargs):
        raise AssertionError("Confirmation must not calculate or open helper-owned connections")

    for name in ("_calculate_plan_build", "_forecast", "audit_training_plan", "build_plan"):
        monkeypatch.setattr(ps, name, forbidden)
    for name in ("get_activities", "get_athlete_profile", "get_latest_planning_checkpoint",
                 "get_coach_constraints", "set_user_setting", "save_planning_checkpoint"):
        monkeypatch.setattr(db, name, forbidden)
    applied = confirm(db, shown)
    assert checkpoint_payload(db) == json.loads(row["checkpoint_json"])
    expected = {**shown, "plan_id": applied["plan_id"], "confirmation_required": False,
                "confirmation": {**shown["confirmation"], "status": "applied", "replayed": False, "is_current": True}}
    assert applied == expected
    after = protected_state(db)
    assert len(after["checkpoints"]) == len(before["checkpoints"]) + 1
    saved = dict((r[0], r[1]) for r in after["settings"])
    intended = json.loads(row["settings_write_json"])
    assert saved["planning_demand_level"] == intended["planning_demand_level"]
    profile = json.loads(saved["planning_profile"])
    assert profile.pop("updated_at")
    assert profile == intended["planning_profile"]


@pytest.mark.parametrize("change", ["activity", "profile", "constraint", "demand", "planning_profile", "base", "day", "timezone", "rules"])
def test_stale_invalidates_only_preview(tmp_path, monkeypatch, change):
    db = seeded_db(tmp_path, existing=True)
    shown = prepare(db)
    if change == "activity":
        add_late_activity(db)
    elif change == "profile":
        execute(db, "UPDATE athlete_profile SET ftp=ftp+1")
    elif change == "constraint":
        db.save_coach_constraint(date="2026-11-10", kind="forced_rest")
    elif change in {"demand", "planning_profile"}:
        db.set_user_setting("planning_demand_level" if change == "demand" else change, "changed")
    elif change == "base":
        db.save_planning_checkpoint({"goal_type": "synthetic", "distance": "synthetic"})
    elif change == "day":
        monkeypatch.setattr(ps, "athlete_local_date", lambda: TODAY + timedelta(days=1))
    elif change == "timezone":
        monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/London")
    else:
        monkeypatch.setattr(protocol, "PLANNING_BUILD_RULE_VERSION", "changed")
    before = protected_state(db)
    error_code(db, shown, "preview_stale")
    error_code(db, shown, "preview_invalidated")
    assert protected_state(db) == before


def test_replay_survives_restart_expiry_rules_and_later_plan(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    shown = prepare(db)
    applied = confirm(db, shown)
    later = prepare(db)
    confirm(db, later)
    add_late_activity(db)
    monkeypatch.setattr(protocol, "PLANNING_BUILD_RULE_VERSION", "changed")
    monkeypatch.setattr(ps, "athlete_local_date", lambda: TODAY + timedelta(days=90))
    monkeypatch.setattr(ps, "_capture_plan_build_inputs", lambda *a, **k: pytest.fail("Replay must not recapture"))
    reopened = Database(db.db_path)
    before = protected_state(reopened)
    replay = confirm(reopened, shown)
    assert replay == {**applied, "confirmation": {**applied["confirmation"], "replayed": True, "is_current": False}}
    assert protected_state(reopened) == before


@pytest.mark.parametrize("field", ["checkpoint_json", "response_json", "parameters_json", "schema_version", "applied_response_json", "receipt_digest", "missing_checkpoint"])
def test_corrupt_or_missing_receipt_never_rebuilds(tmp_path, field):
    db = seeded_db(tmp_path)
    shown = prepare(db)
    applied = confirm(db, shown)
    token = shown["confirmation"]["preview_id"]
    if field == "missing_checkpoint":
        execute(db, "DELETE FROM planning_checkpoints WHERE id=?", (int(applied["plan_id"]),))
    else:
        value = 999 if field == "schema_version" else "broken"
        execute(db, f"UPDATE planning_build_previews SET {field}=? WHERE preview_id=?", (value, token))
    before = protected_state(db)
    error_code(db, shown, "preview_checkpoint_missing" if field == "missing_checkpoint" else "preview_corrupt")
    assert protected_state(db) == before


def test_unknown_wrong_database_and_origin_fail_closed(tmp_path):
    db = seeded_db(tmp_path)
    shown = prepare(db, origin="coach")
    before = protected_state(db)
    error_code(db, shown, "preview_not_found")
    shown["confirmation"]["preview_id"] = str(uuid4())
    error_code(db, shown, "preview_not_found")
    other = Database(str(tmp_path / "other.db"))
    error_code(other, prepare(db), "preview_not_found")
    assert protected_state(db) == before


class ConnectionProxy:
    def __init__(self, conn, *, before_begin=None, commit=None):
        self.conn, self.before_begin, self.commit_hook = conn, before_begin, commit

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def execute(self, sql, *args):
        if sql == "BEGIN IMMEDIATE" and self.before_begin:
            self.before_begin()
        return self.conn.execute(sql, *args)

    def commit(self):
        if self.commit_hook:
            return self.commit_hook(self.conn)
        return self.conn.commit()


@pytest.mark.parametrize("existing", [False, True], ids=["first-insert", "existing-update"])
@pytest.mark.parametrize("stage", ["checkpoint", "demand", "profile", "receipt", "commit", "invalidation"])
def test_each_write_failure_rolls_back(tmp_path, monkeypatch, stage, existing):
    db = seeded_db(tmp_path, existing=existing)
    if not existing:
        db.delete_user_setting("planning_demand_level")
        db.delete_user_setting("planning_profile")
    shown = prepare(db)
    if stage == "invalidation":
        add_late_activity(db)
    if stage in {"receipt", "invalidation"}:
        table, event, condition = "planning_build_previews", "UPDATE", "1"
    elif stage == "checkpoint":
        table, event, condition = "planning_checkpoints", "INSERT", "1"
    else:
        table, event = "user_settings", "UPDATE" if existing else "INSERT"
        condition = f"NEW.key = '{'planning_profile' if stage == 'profile' else 'planning_demand_level'}'"
    if stage != "commit":
        execute(db, f"CREATE TRIGGER fail_write AFTER {event} ON {table} WHEN {condition} "
                    "BEGIN SELECT RAISE(ABORT, 'synthetic write failure'); END")
    before = protected_state(db)
    row_before = get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui")
    if stage == "commit":
        connect = db._connect

        def fail_commit(conn):
            raise sqlite3.OperationalError("synthetic commit failure")

        monkeypatch.setattr(db, "_connect", lambda: ConnectionProxy(connect(), commit=fail_commit))
    error = error_code(db, shown, "planning_storage_error")
    assert error.retryable is True
    assert protected_state(db) == before
    assert get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui") == row_before


def test_lost_post_commit_result_retries_same_receipt(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    shown = prepare(db)
    connect = db._connect

    def lost(conn):
        conn.commit()
        raise sqlite3.OperationalError("synthetic lost commit response")

    monkeypatch.setattr(db, "_connect", lambda: ConnectionProxy(connect(), commit=lost))
    error_code(db, shown, "planning_storage_error")
    monkeypatch.setattr(db, "_connect", connect)
    before = protected_state(db)
    replay = confirm(db, shown)
    assert replay["confirmation"]["replayed"] is True
    assert len(before["checkpoints"]) == 1
    assert protected_state(db) == before


@pytest.mark.parametrize("same_preview", [False, True])
def test_two_real_confirm_connections_serialize(tmp_path, monkeypatch, same_preview):
    db = seeded_db(tmp_path)
    first = prepare(db)
    second = first if same_preview else prepare(db)
    barrier = Barrier(2)
    connect = db._connect
    monkeypatch.setattr(db, "_connect", lambda: ConnectionProxy(connect(), before_begin=lambda: barrier.wait(5)))

    def attempt(shown):
        try:
            return confirm(db, shown)
        except PlanningBuildPreviewError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [first, second]))
    monkeypatch.setattr(db, "_connect", connect)
    assert len(protected_state(db)["checkpoints"]) == 1
    if same_preview:
        assert sorted(r["confirmation"]["replayed"] for r in results) == [False, True]
        assert results[0]["plan_id"] == results[1]["plan_id"]
    else:
        assert sum(isinstance(r, dict) for r in results) == 1
        assert "preview_stale" in results


def test_dependency_writer_blocked_until_after_confirm_is_later_event(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    shown = prepare(db)
    checking, blocked, committed = Event(), Event(), Event()
    read_latest = db._get_latest_planning_checkpoint

    def at_check(conn):
        checking.set()
        assert blocked.wait(5)
        return read_latest(conn)

    monkeypatch.setattr(db, "_get_latest_planning_checkpoint", at_check)

    def writer():
        assert checking.wait(5)
        conn = db._connect()
        try:
            conn.execute("PRAGMA busy_timeout=0")
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                conn.execute("BEGIN IMMEDIATE")
            blocked.set()
            assert committed.wait(5)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE athlete_profile SET ftp=ftp+1")
            conn.commit()
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        applied = confirm(db, shown)
        committed.set()
        future.result(timeout=5)
    assert applied["confirmation"]["status"] == "applied"
    assert confirm(db, shown)["confirmation"]["replayed"] is True


def test_busy_keeps_identity_pending_and_retry_succeeds(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    shown = prepare(db)
    connect = db._connect

    def short_wait():
        conn = connect()
        conn.execute("PRAGMA busy_timeout=0")
        return conn

    monkeypatch.setattr(db, "_connect", short_wait)
    blocker = connect()
    try:
        blocker.execute("BEGIN IMMEDIATE")
        error = error_code(db, shown, "planning_busy")
        assert error.status == 503 and error.retryable is True
    finally:
        blocker.rollback()
        blocker.close()
    assert confirm(db, shown)["confirmation"]["status"] == "applied"


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_confirmation_expiry_boundary_is_checked_under_lock(tmp_path, monkeypatch, delta):
    from datetime import datetime

    db = seeded_db(tmp_path)
    shown = prepare(db)
    expiry = datetime.fromisoformat(shown["confirmation"]["expires_at"].replace("Z", "+00:00"))
    instant = expiry + timedelta(microseconds=delta)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(ps, "datetime", Clock)
    before = protected_state(db)
    if delta < 0:
        assert confirm(db, shown)["plan_id"]
    else:
        error = error_code(db, shown, "preview_expired")
        assert error.status == 410 and not error.retryable
        assert protected_state(db) == before
        assert get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui")["state"] == "pending"


def test_expired_successful_receipt_replays_after_restart_and_backup(tmp_path, monkeypatch):
    from datetime import datetime
    from scripts.sqlite_backup_restore import backup_database, restore_database

    db = seeded_db(tmp_path)
    shown = prepare(db)
    applied = confirm(db, shown)
    expiry = datetime.fromisoformat(shown["confirmation"]["expires_at"].replace("Z", "+00:00"))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = expiry + timedelta(days=30)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(ps, "datetime", Clock)
    backup, restored_path = tmp_path / "backup.db", tmp_path / "restored.db"
    backup_database(db.db_path, backup, confirm_stopped=True)
    restore_database(backup, restored_path, confirm_stopped=True)
    restored = Database(str(restored_path))
    before = protected_state(restored)
    replay = confirm(restored, shown)
    assert replay == {**applied, "confirmation": {**applied["confirmation"], "replayed": True}}
    assert protected_state(restored) == before


def test_confirm_owns_one_closed_connection_and_one_transaction(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    shown = prepare(db)
    connect = db._connect
    opened = []

    def trace():
        conn = connect()
        sql = []
        conn.set_trace_callback(sql.append)
        opened.append((conn, sql))
        return conn

    monkeypatch.setattr(db, "_connect", trace)
    confirm(db, shown)
    assert len(opened) == 1
    conn, sql = opened[0]
    assert sql[0] == "BEGIN IMMEDIATE" and sql[-1] == "COMMIT"
    for table in ("activities AS a", "athlete_profile", "coach_constraints", "user_settings", "planning_checkpoints"):
        assert any(query.lstrip().startswith("SELECT") and table in query for query in sql), table
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")


@pytest.mark.parametrize("change,stale", [
    ("update_activity", True), ("delete_activity", True), ("provider_link", True),
    ("deactivate_constraint", True), ("same_id_checkpoint", True), ("cutoff", True),
    ("absent_to_null", True), ("theme", False), ("hrv", False), ("old_activity", False),
    ("outside_constraint", False), ("identical_values", False),
])
def test_full_dependency_contract_at_confirmation(tmp_path, monkeypatch, change, stale):
    db = seeded_db(tmp_path, existing=True)
    if change == "absent_to_null":
        db.delete_user_setting("planning_profile")
    shown = prepare(db)
    if change == "update_activity":
        execute(db, "UPDATE activities SET tss=tss+1 WHERE activity_id='s0'")
    elif change == "delete_activity":
        execute(db, "DELETE FROM activities WHERE activity_id='s0'")
    elif change == "provider_link":
        execute(db, "INSERT INTO activity_provider_links(canonical_activity_id,provider,provider_activity_id,"
                    "external_provider,external_id) VALUES('s0','intervals','synthetic-link','garmin','linked')")
    elif change == "deactivate_constraint":
        db.deactivate_coach_constraint(1)
    elif change == "same_id_checkpoint":
        execute(db, "UPDATE planning_checkpoints SET checkpoint_data=json_set(checkpoint_data,'$.synthetic',1)")
    elif change == "cutoff":
        monkeypatch.setattr(db, "_cutoff_date", lambda _: "2026-07-19")
    elif change == "absent_to_null":
        db.set_user_setting("planning_profile", None)
    elif change == "theme":
        db.set_user_setting("theme", "light")
    elif change == "hrv":
        db.save_hrv_data({TODAY.isoformat(): {"rmssd": 42}})
    elif change == "old_activity":
        db.save_activities([{"activity_id": "old", "date": "2026-01-01", "sport": "cycling", "tss": 100}])
    elif change == "outside_constraint":
        db.save_coach_constraint(date="2027-01-01", kind="forced_rest")
    else:
        execute(db, "UPDATE activities SET tss=tss WHERE activity_id='s0'")
    before = protected_state(db)
    if stale:
        error_code(db, shown, "preview_stale")
        assert protected_state(db) == before
    else:
        assert confirm(db, shown)["plan_id"]


def test_writer_committed_before_confirm_lock_is_visible(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    shown = prepare(db)
    writer_ready, confirm_started = Event(), Event()
    connect = db._connect

    def writer():
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE athlete_profile SET ftp=ftp+1")
            writer_ready.set()
            assert confirm_started.wait(5)
            conn.commit()
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        assert writer_ready.wait(5)
        monkeypatch.setattr(db, "_connect", lambda: ConnectionProxy(connect(), before_begin=confirm_started.set))
        error_code(db, shown, "preview_stale")
        future.result(timeout=5)
    assert not protected_state(db)["checkpoints"]


def test_precommit_response_validation_failure_rolls_back(tmp_path, monkeypatch):
    from data import planning_build_preview_store as store

    db = seeded_db(tmp_path)
    shown = prepare(db)
    response = store._applied_response

    def invalid(row, checkpoint_id):
        result = response(row, checkpoint_id)
        result["weeks"] = "invalid"
        return result

    monkeypatch.setattr(store, "_applied_response", invalid)
    before = protected_state(db)
    error_code(db, shown, "preview_corrupt")
    assert protected_state(db) == before
    assert get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui")["state"] == "pending"

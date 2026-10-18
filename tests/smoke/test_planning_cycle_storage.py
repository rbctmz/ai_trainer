"""M2 storage/projection acceptance; commands and HTTP remain M3 obligations."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import sqlite3

import pytest

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from scripts.sqlite_backup_restore import backup_database, restore_database
from tests.smoke._planning_cycle_regressions import (
    TODAY, evidence_bytes, first_session_id, legacy_db, pin_clock, plan, seed_evidence,
)

pytestmark = pytest.mark.smoke


def current(db):
    from services.planning_cycles import current_cycle_context
    return current_cycle_context(db)


def historical(db, cycle_id):
    from services.planning_cycles import historical_cycle_context
    return historical_cycle_context(db, cycle_id)


def rows(db, table):
    conn = db._connect()
    try:
        return conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    finally:
        conn.close()


def cycle_rows(db):
    return {table: rows(db, table) for table in (
        "planning_cycle_state", "planning_cycles", "planning_cycle_versions", "planning_cycle_commands",
    )}


def simulate_stored_close(db, cycle_id):
    """Seed the durable post-command state, not an implementation of close/CAS."""
    conn = db._connect()
    try:
        with conn:
            conn.execute("UPDATE planning_cycles SET status='closed', revision=revision+1, "
                         "closed_at='2026-10-16T09:00:00Z' WHERE id=?", (cycle_id,))
            conn.execute("UPDATE planning_cycle_state SET current_cycle_id=NULL, revision=revision+1")
    finally:
        conn.close()


@pytest.mark.parametrize(("start", "days", "state"), [
    (date(2026, 10, 19), 7, "scheduled"),
    (TODAY, 7, "in_progress"),
    (date(2026, 10, 12), 5, "in_progress"),
    (date(2026, 10, 12), 4, "period_ended"),
])
def test_selected_projection_uses_inclusive_actual_bounds(tmp_path, monkeypatch, start, days, state):
    from datetime import timedelta

    db = legacy_db(tmp_path, monkeypatch, start=start, days=days)
    result = current(db)
    assert result["state"] == state
    assert result["start_date"] == start.isoformat()
    assert result["end_date"] == (start + timedelta(days=days - 1)).isoformat()
    assert result["cycle_id"] == result["current_cycle_id"]
    assert result["checkpoint_id"] == 1 and result["is_legacy"] is True
    assert result["athlete_day"] == TODAY.isoformat()
    assert result["athlete_timezone"] == "Europe/Moscow"
    assert result["current_week"] is None if state != "in_progress" else result["current_week"]
    if state == "period_ended":
        assert result["last_week"]["phase"] == "Race Week"
        assert result["last_week"]["is_historical"] is True
        assert "edit_current" not in result["allowed_actions"]
    assert all(event["outcome"] == "unspecified" for event in result["events"])


@pytest.mark.parametrize(("zone", "day", "state"), [
    ("Europe/Moscow", "2026-10-17", "period_ended"),
    ("Pacific/Honolulu", "2026-10-16", "in_progress"),
])
def test_context_captures_athlete_day_once(tmp_path, monkeypatch, zone, day, state):
    db = legacy_db(tmp_path, monkeypatch, start=date(2026, 10, 12), days=5)
    pin_clock(monkeypatch, observed=datetime(2026, 10, 16, 21, 30, tzinfo=timezone.utc), zone=zone)
    context = current(db)
    assert (context["athlete_day"], context["state"]) == (day, state)


@pytest.mark.parametrize("damage", ["bad-json", "missing-plan", "missing-days", "bad-date", "duplicate", "reverse", "nan-load"])
def test_malformed_latest_is_indeterminate_without_older_fallback(tmp_path, monkeypatch, damage):
    old = build_planning_checkpoint(plan())
    latest = build_planning_checkpoint(plan(date(2026, 10, 12)))
    daily = latest["goal_plan_snapshot"]["daily_plan"]
    if damage == "bad-json":
        latest = "{broken"
    elif damage == "missing-plan":
        latest = {"event_date": "2026-12-31", "weeks_to_race": 10}
    elif damage == "missing-days":
        latest["goal_plan_snapshot"]["daily_plan"] = []
    elif damage == "bad-date":
        daily[0]["date"] = "2026-02-30"
    elif damage == "duplicate":
        daily[1]["date"] = daily[0]["date"]
    elif damage == "reverse":
        daily.reverse()
    else:
        daily[0]["total_tss"] = float("nan")
    db = legacy_db(tmp_path, monkeypatch, payloads=[old, latest])
    result = current(db)
    assert result["state"] == "indeterminate"
    assert result["checkpoint_id"] == 2
    assert result["start_date"] is result["end_date"] is None
    assert result["reason_code"]
    assert result["current_week"] is None
    assert "edit_current" not in result["allowed_actions"]
    assert [row[0] for row in rows(db, "planning_cycle_versions")] == [2]


def test_import_only_latest_preserves_exact_legacy_json(tmp_path, monkeypatch):
    raw = json.dumps(build_planning_checkpoint(plan()), ensure_ascii=False, indent=3)
    db = legacy_db(tmp_path, monkeypatch, payloads=[raw, raw])
    before = rows(db, "planning_checkpoints")
    context = current(db)
    assert context["checkpoint_id"] == 2
    assert db.get_current_planning_checkpoint()["id"] == 2
    assert len(rows(db, "planning_cycles")) == 1
    assert rows(db, "planning_cycle_versions") == [(2, context["cycle_id"], "initial")]
    assert [row[4] for row in before] == [raw, raw]
    persisted = cycle_rows(db)
    reopened = Database(db.db_path)
    assert cycle_rows(reopened) == persisted
    assert rows(reopened, "planning_checkpoints") == before


def test_null_selection_never_imports_later_raw_history(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, payloads=[])
    before = cycle_rows(db)
    assert current(db)["state"] == "no_current"
    assert current(db)["has_history"] is False
    saved = db.save_planning_checkpoint(build_planning_checkpoint(plan()))
    reopened = Database(db.db_path)
    assert current(reopened)["state"] == "no_current"
    assert current(reopened)["has_history"] is True
    assert reopened.get_current_planning_checkpoint() is None
    assert reopened.get_latest_planning_checkpoint()["id"] == saved["id"]
    assert cycle_rows(reopened) == before


def test_higher_history_id_does_not_replace_selected_checkpoint(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    selected = current(db)
    db.save_planning_checkpoint(build_planning_checkpoint(plan(date(2026, 11, 2))))
    assert db.get_latest_planning_checkpoint()["id"] == 2
    assert db.get_current_planning_checkpoint()["id"] == 1
    assert current(db) == selected
    assert current(Database(db.db_path)) == selected


def test_closed_null_and_outcome_stay_historical_after_restart(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    old = current(db)
    simulate_stored_close(db, old["cycle_id"])
    before = {**evidence_bytes(db), **cycle_rows(db)}
    reopened = Database(db.db_path)
    assert current(reopened)["state"] == "no_current"
    assert reopened.get_current_planning_checkpoint() is None
    previous = historical(reopened, old["cycle_id"])
    assert previous["state"] == "closed"
    assert previous["is_selected"] is False and previous["current_cycle_id"] is None
    assert previous["checkpoint_id"] == old["checkpoint_id"]
    assert previous["events"][0]["outcome"] == "unspecified"
    assert {**evidence_bytes(reopened), **cycle_rows(reopened)} == before


def test_read_does_not_write_or_initialize_missing_state(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = {**evidence_bytes(db), **cycle_rows(db)}
    for _ in range(3):
        result = current(db)
        historical(db, result["cycle_id"])
        db.get_current_planning_checkpoint()
    assert {**evidence_bytes(db), **cycle_rows(db)} == before
    conn = db._connect()
    try:
        with conn:
            conn.execute("DELETE FROM planning_cycle_state")
    finally:
        conn.close()
    from models.planning_cycle import CycleStateCorrupt
    with pytest.raises(CycleStateCorrupt):
        current(db)
    assert rows(db, "planning_cycle_state") == []


@pytest.mark.parametrize("damage", ["missing-cycle", "missing-checkpoint", "wrong-map", "closed-selected", "wrong-bounds"])
def test_corrupt_selected_links_fail_closed(tmp_path, monkeypatch, damage):
    db = legacy_db(tmp_path, monkeypatch)
    context = current(db)
    conn = db._connect()
    try:
        with conn:
            if damage == "missing-cycle":
                conn.execute("DELETE FROM planning_cycles")
            elif damage == "missing-checkpoint":
                conn.execute("DELETE FROM planning_checkpoints")
            elif damage == "wrong-map":
                conn.execute("DELETE FROM planning_cycle_versions")
            elif damage == "closed-selected":
                conn.execute("UPDATE planning_cycles SET status='closed'")
            else:
                conn.execute("UPDATE planning_cycles SET end_date='2026-12-31'")
    finally:
        conn.close()
    result = current(db)
    assert result["state"] == "indeterminate"
    assert result["cycle_id"] == context["cycle_id"]
    assert result["reason_code"]
    assert db.get_current_planning_checkpoint() is None


def test_reader_uses_one_wal_snapshot(tmp_path, monkeypatch):
    from data.planning_cycles import PlanningCycleStore

    db = legacy_db(tmp_path, monkeypatch)
    context = current(db)
    reader = db._connect()
    try:
        reader.execute("BEGIN")
        store = PlanningCycleStore(reader)
        assert store.state()["current_cycle_id"] == context["cycle_id"]
        simulate_stored_close(db, context["cycle_id"])
        assert db._get_current_planning_checkpoint(reader)["id"] == context["checkpoint_id"]
        assert store.cycle(context["cycle_id"])["status"] == "open"
    finally:
        reader.rollback()
        reader.close()
    assert db.get_current_planning_checkpoint() is None


def test_backup_restore_preserves_cycles_receipts_namespace_and_ledgers(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    seed_evidence(db, first_session_id(plan()))
    context = current(db)
    simulate_stored_close(db, context["cycle_id"])
    # Storage retention only: M3 will prove command/result/idempotency semantics.
    conn = db._connect()
    try:
        with conn:
            conn.execute("INSERT INTO planning_cycle_commands "
                         "(command_id,kind,request_digest,cycle_id,request_json,result_json) "
                         "VALUES ('synthetic-command','close','synthetic-digest',?,'{}','{}')", (context["cycle_id"],))
    finally:
        conn.close()
    before = {**evidence_bytes(db), **cycle_rows(db)}
    backup_database(db.db_path, tmp_path / "snapshot.db", confirm_stopped=True)
    restore_database(tmp_path / "snapshot.db", tmp_path / "restore.db", confirm_stopped=True)
    reopened = Database(str(tmp_path / "restore.db"))
    assert {**evidence_bytes(reopened), **cycle_rows(reopened)} == before
    assert current(reopened)["state"] == "no_current"


def test_full_reset_clears_cycle_rows_and_previews_without_resurrection(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = current(db)
    db.clear_all_data()
    reopened = Database(db.db_path)
    assert current(reopened)["state"] == "no_current"
    assert current(reopened)["has_history"] is False
    assert rows(reopened, "planning_cycles") == []
    assert rows(reopened, "planning_cycle_versions") == []
    assert rows(reopened, "planning_cycle_commands") == []
    assert rows(reopened, "planning_build_previews") == []
    assert len(rows(reopened, "planning_cycle_state")) == 1
    assert current(reopened)["selection_revision"] == 0
    assert before["cycle_id"] not in str(cycle_rows(reopened))


@pytest.mark.parametrize("fault_table", ["planning_cycles", "planning_cycle_versions", "planning_cycle_state"])
def test_failed_migration_rolls_back_and_can_retry(tmp_path, monkeypatch, fault_table):
    db = legacy_db(tmp_path, monkeypatch)
    # Recreate a pre-migration database containing the same untouched old rows.
    conn = db._connect()
    try:
        with conn:
            for table in ("planning_cycle_commands", "planning_cycle_versions", "planning_cycles", "planning_cycle_state"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute(f"CREATE TRIGGER m2_abort BEFORE INSERT ON {fault_table} "
                         "BEGIN SELECT RAISE(ABORT, 'synthetic migration fault'); END")
    finally:
        conn.close()
    before = evidence_bytes(db)
    with pytest.raises(sqlite3.IntegrityError, match="synthetic migration fault"):
        Database(db.db_path)
    assert evidence_bytes(db) == before
    assert all(not value for value in cycle_rows(db).values())
    conn = db._connect()
    try:
        with conn:
            conn.execute("DROP TRIGGER m2_abort")
    finally:
        conn.close()
    assert current(Database(db.db_path))["checkpoint_id"] == 1

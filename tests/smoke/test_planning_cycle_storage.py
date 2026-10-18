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
    CYCLE_A, CYCLE_B, TODAY, evidence_bytes, first_session_id, legacy_db, pin_clock, plan, seed_evidence,
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
    if state == "in_progress":
        assert result["current_week"]["phase"] == "Race Week"
    else:
        assert result["current_week"] is None
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


@pytest.mark.parametrize("damage", ["bad-json", "missing-plan", "missing-days", "bad-date", "duplicate", "reverse", "nan-load", "bad-templates", "bad-sessions"])
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
    elif damage == "bad-templates":
        latest["goal_plan_snapshot"]["session_templates"] = 5
    elif damage == "bad-sessions":
        latest["goal_plan_snapshot"]["session_templates"][0]["sessions"] = 5
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
                # Deliberately bypass the DDL guard to simulate damaged storage.
                conn.execute("DROP TRIGGER planning_cycle_versions_no_delete")
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
    if damage in {"missing-cycle", "missing-checkpoint", "wrong-map"}:
        assert result["events"] == []
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
                         "VALUES (?,'close','synthetic-digest',?,'{}','{}')", (CYCLE_B, context["cycle_id"]))
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
            conn.execute("DROP TRIGGER planning_cycle_versions_no_delete")
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


@pytest.mark.parametrize(("binding", "expected"), [
    ("selected-plan", "cycle"), ("old-plan", "unknown"), ("absent-plan", "unknown"),
    ("unique-session", "cycle"), ("ambiguous-session", "unknown"),
    ("selected-plan-missing-session", "unknown"), ("old-plan-current-session", "unknown"),
    ("selected-plan-ambiguous-session", "cycle"),
])
def test_constraint_import_requires_unambiguous_stored_ownership(tmp_path, monkeypatch, binding, expected):
    older = build_planning_checkpoint(plan())
    latest = older if "ambiguous-session" in binding else build_planning_checkpoint(plan(date(2026, 11, 2)))
    sid = latest["goal_plan_snapshot"]["session_templates"][0]["sessions"][0]["session_id"]
    original = []

    def before_init(conn):
        plan_id = {"selected-plan": "2", "old-plan": "1", "absent-plan": "999",
                   "selected-plan-missing-session": "2", "old-plan-current-session": "1",
                   "selected-plan-ambiguous-session": "2"}.get(binding)
        session_id = ("absent-session" if binding == "selected-plan-missing-session" else sid
                      if "session" in binding else None)
        conn.execute("UPDATE coach_constraints SET plan_id=?,session_id=?,sport='run',note='Synthetic note'",
                     (plan_id, session_id))
        original.extend(conn.execute("SELECT * FROM coach_constraints").fetchall())

    db = legacy_db(tmp_path, monkeypatch, payloads=[older, latest], constraint_kind="manual_delete",
                   before_init=before_init)
    constraint = db.get_coach_constraint(1)
    assert constraint["cycle_scope"] == expected
    assert constraint["cycle_id"] == (current(db)["cycle_id"] if expected == "cycle" else None)
    assert rows(db, "coach_constraints")[0][:12] == original[0]
    before = rows(db, "coach_constraints")
    assert rows(Database(db.db_path), "coach_constraints") == before


def test_migration_keeps_all_old_history_and_fact_bytes(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    seed_evidence(db, first_session_id(plan()))
    conn = db._connect()
    try:
        with conn:
            conn.execute("DROP TRIGGER planning_cycle_versions_no_delete")
            for table in ("planning_cycle_commands", "planning_cycle_versions", "planning_cycles", "planning_cycle_state"):
                conn.execute(f"DELETE FROM {table}")
    finally:
        conn.close()
    before = evidence_bytes(db)
    reopened = Database(db.db_path)
    assert current(reopened)["checkpoint_id"] == 1
    assert evidence_bytes(reopened) == before


def test_cycle_ddl_columns_import_and_flag_roll_back_together(tmp_path, monkeypatch):
    from data import database as db_module

    original = db_module.initialize_cycle_store

    def abort_after_flag(conn):
        original(conn)
        raise sqlite3.IntegrityError("synthetic post-flag fault")

    with monkeypatch.context() as fault:
        fault.setattr(db_module, "initialize_cycle_store", abort_after_flag)
        with pytest.raises(sqlite3.IntegrityError, match="synthetic post-flag fault"):
            legacy_db(tmp_path, fault, constraint_kind="manual_delete")
    with sqlite3.connect(tmp_path / "plan.db") as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not {table for table in tables if table.startswith("planning_cycle")}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(coach_constraints)")}
        assert "cycle_scope" not in columns and "cycle_id" not in columns
        raw = conn.execute("SELECT checkpoint_data FROM planning_checkpoints").fetchone()[0]
    pin_clock(monkeypatch)
    reopened = Database(str(tmp_path / "plan.db"))
    assert current(reopened)["checkpoint_id"] == 1
    assert rows(reopened, "planning_checkpoints")[0][4] == raw


def test_full_reset_rolls_back_cycle_state_when_other_delete_fails(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = {**evidence_bytes(db), **cycle_rows(db)}
    conn = db._connect()
    try:
        with conn:
            conn.execute("CREATE TRIGGER m2_reset_abort BEFORE DELETE ON activities "
                         "BEGIN SELECT RAISE(ABORT, 'synthetic reset fault'); END")
    finally:
        conn.close()
    with pytest.raises(sqlite3.IntegrityError, match="synthetic reset fault"):
        db.clear_all_data()
    assert {**evidence_bytes(db), **cycle_rows(db)} == before
    conn = db._connect()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with conn:
                conn.execute("DELETE FROM planning_cycle_versions")
    finally:
        conn.close()
    assert current(Database(db.db_path))["checkpoint_id"] == 1


def test_event_keys_use_cycle_and_provider_source_identity(tmp_path, monkeypatch):
    from models.planning_cycle import cycle_events

    checkpoint = build_planning_checkpoint(plan())
    event = checkpoint["goal_plan_snapshot"]["events"][0]
    checkpoint["goal_plan_snapshot"]["events"] = [
        {**event, "source": "intervals_icu", "source_id": "e1"},
        {**event, "source": "intervals_icu", "source_id": "e2"},
    ]
    a = cycle_events({"id": CYCLE_A}, checkpoint)
    b = cycle_events({"id": CYCLE_B}, checkpoint)
    assert len({row["event_key"] for row in a}) == 2
    assert not any(row["is_ambiguous"] for row in a)
    assert {row["event_key"] for row in a}.isdisjoint(row["event_key"] for row in b)


def test_selected_reads_succeed_with_writes_forbidden(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    original = db._connect

    def read_only():
        conn = original()
        writes = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                  sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_DROP_TABLE}
        conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action in writes else sqlite3.SQLITE_OK)
        return conn

    monkeypatch.setattr(db, "_connect", read_only)
    context = current(db)
    assert db.get_current_planning_checkpoint()["id"] == context["checkpoint_id"]
    assert historical(db, context["cycle_id"])["cycle_id"] == context["cycle_id"]


def test_connection_bound_selector_requires_a_transaction(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    conn = db._connect()
    try:
        with pytest.raises(RuntimeError, match="requires a transaction"):
            db._get_current_planning_checkpoint(conn)
    finally:
        conn.close()


@pytest.mark.parametrize("statement", [
    "UPDATE planning_cycle_versions SET cycle_id=? WHERE checkpoint_id=1",
    "INSERT OR REPLACE INTO planning_cycle_versions VALUES (1,?,'restore')",
    "DELETE FROM planning_cycle_versions WHERE checkpoint_id=1 AND ? IS NOT NULL",
    "DELETE FROM planning_cycle_versions WHERE ? IS NOT NULL",
])
def test_checkpoint_cycle_association_is_immutable(tmp_path, monkeypatch, statement):
    db = legacy_db(tmp_path, monkeypatch)
    before = cycle_rows(db)
    conn = db._connect()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with conn:
                conn.execute(statement, (CYCLE_B,))
    finally:
        conn.close()
    assert cycle_rows(db) == before


def test_concurrent_initialization_imports_exactly_once(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    db = legacy_db(tmp_path, monkeypatch)
    conn = db._connect()
    try:
        with conn:
            conn.execute("DROP TRIGGER planning_cycle_versions_no_delete")
            for table in ("planning_cycle_commands", "planning_cycle_versions", "planning_cycles", "planning_cycle_state"):
                conn.execute(f"DELETE FROM {table}")
    finally:
        conn.close()
    barrier = threading.Barrier(2)

    def initialize():
        barrier.wait(timeout=5)
        return current(Database(db.db_path))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: initialize(), range(2)))
    assert results[0] == results[1]
    assert len(rows(db, "planning_cycles")) == len(rows(db, "planning_cycle_versions")) == 1


def test_history_identifies_current_selection_without_reselecting_old_cycle(tmp_path, monkeypatch):
    from services import planning_cycles

    db = legacy_db(tmp_path, monkeypatch)
    old = current(db)
    saved = db.save_planning_checkpoint(build_planning_checkpoint(plan(date(2026, 11, 2))))
    simulate_stored_close(db, old["cycle_id"])
    conn = db._connect()
    try:
        with conn:
            conn.execute("INSERT INTO planning_cycles "
                         "(id,current_checkpoint_id,revision,status,start_date,end_date,origin) "
                         "VALUES (?,?,1,'open','2026-11-02','2026-11-08','explicit')", (CYCLE_B, saved["id"]))
            conn.execute("INSERT INTO planning_cycle_versions VALUES (?,?,'initial')", (saved["id"], CYCLE_B))
            conn.execute("UPDATE planning_cycle_state SET current_cycle_id=?,revision=revision+1", (CYCLE_B,))
    finally:
        conn.close()
    calls = []

    def one_day():
        calls.append(True)
        return TODAY

    monkeypatch.setattr(planning_cycles, "athlete_local_date", one_day)
    before = cycle_rows(db)
    history = planning_cycles.cycle_history(db)
    assert len(calls) == 1
    contexts = {context["cycle_id"]: context for context in history}
    assert contexts[old["cycle_id"]]["state"] == "closed"
    assert contexts[old["cycle_id"]]["current_cycle_id"] == CYCLE_B
    assert contexts[old["cycle_id"]]["is_selected"] is False
    assert contexts[CYCLE_B]["is_selected"] is True
    assert len(planning_cycles.cycle_history(db, limit=1)) == 1
    assert cycle_rows(db) == before


def test_missing_historical_cycle_is_not_current_fallback(tmp_path, monkeypatch):
    from models.planning_cycle import CycleNotFound

    db = legacy_db(tmp_path, monkeypatch)
    with pytest.raises(CycleNotFound):
        historical(db, CYCLE_B)


@pytest.mark.parametrize("outcome", ["{broken", "[]", '{"key":"won"}'])
def test_malformed_known_outcome_is_gap_not_inferred_participation(tmp_path, monkeypatch, outcome):
    db = legacy_db(tmp_path, monkeypatch)
    conn = db._connect()
    try:
        with conn:
            conn.execute("UPDATE planning_cycles SET event_outcomes_json=?", (outcome,))
    finally:
        conn.close()
    context = current(db)
    assert context["state"] == "indeterminate"
    assert context["reason_code"] == "cycle_outcomes_invalid"
    assert context["events"] == []


def test_indeterminate_readable_snapshot_keeps_ordinary_checkpoint_shape(tmp_path, monkeypatch):
    checkpoint = build_planning_checkpoint(plan())
    checkpoint["goal_plan_snapshot"]["daily_plan"] = []
    db = legacy_db(tmp_path, monkeypatch, payloads=[checkpoint])
    assert current(db)["state"] == "indeterminate"
    assert db.get_current_planning_checkpoint() == db.get_planning_checkpoint(1)


def test_no_event_cycle_has_no_participation_action(tmp_path, monkeypatch):
    goal = plan()
    goal.update(planning_mode="training_goal", events=[], event_date=None)
    db = legacy_db(tmp_path, monkeypatch, payloads=[build_planning_checkpoint(goal)])
    context = current(db)
    assert context["events"] == []
    simulate_stored_close(db, context["cycle_id"])
    closed = historical(db, context["cycle_id"])
    assert "set_event_outcome" not in closed["allowed_actions"]


def test_unselected_open_record_is_not_inferred_current_or_closed(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    old = current(db)
    conn = db._connect()
    try:
        with conn:
            conn.execute("UPDATE planning_cycle_state SET current_cycle_id=NULL, revision=revision+1")
    finally:
        conn.close()
    assert current(db)["state"] == "no_current"
    orphan = historical(db, old["cycle_id"])
    assert orphan["state"] == "indeterminate"
    assert orphan["reason_code"] == "cycle_not_selected"
    assert orphan["is_selected"] is False
    assert "edit_current" not in orphan["allowed_actions"]

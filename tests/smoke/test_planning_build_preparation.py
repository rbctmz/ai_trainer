"""M2: frozen preparation is coherent and never publishes active plan state."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
import json
import sqlite3
from threading import Event

import pytest

from api import planning_service as ps
from config.settings import Settings
from data.planning_build_preview_store import get_preview, preview_response, store_pending
from models import planning_build_confirmation as protocol
from models.planning_build_confirmation import BuildParameters, PlanningBuildPreviewError
from tests.smoke._planning_build_confirmation import (
    MODES, TODAY, add_late_activity, characterization, cycle_fields, parameters, pin_clock, protected_state, seeded_db,
)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    pin_clock(monkeypatch)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("existing", [False, True], ids=["first", "existing"])
def test_prepared_payload_preserves_complete_m1_calculation(tmp_path, mode, existing):
    from tests.smoke.test_planning_build_confirmation_storage import BASELINE

    db = seeded_db(tmp_path, existing=existing, rested=True)
    before = protected_state(db)
    # Keep the frozen S1 calculation oracle byte-for-byte. This low-level v1
    # fixture is readable but deliberately NOT eligible for confirmation in S2.
    snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(parameters(mode)))
    prepared = ps._calculate_plan_build(snapshot)
    shown = preview_response(store_pending(db, prepared, origin="planning_ui", now=ps.datetime.now(ps.timezone.utc),
                                          recheck=lambda _conn: snapshot.dependency_digest))
    retained = get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui")
    checkpoint = json.loads(retained["checkpoint_json"])
    public = json.loads(retained["response_json"])
    # Legacy persisted response differed only in these two publication fields;
    # full prepared content must still match the pre-extraction M1 oracle.
    public["confirmation_required"] = False
    expected = json.loads(BASELINE.read_text())["cases"][f"{mode}:{'existing' if existing else 'first'}"]
    assert characterization(public, checkpoint) == expected
    assert protected_state(db) == before
    assert shown["confirmation"]["status"] == "pending"
    assert shown["plan_id"] is None


def pending_count(db):
    conn = db._connect()
    try:
        return conn.execute("SELECT count(*) FROM planning_build_previews").fetchone()[0]
    finally:
        conn.close()


def execute(db, sql, values=()):
    conn = db._connect()
    try:
        with conn:
            conn.execute(sql, values)
    finally:
        conn.close()


def test_capture_and_prepare_use_coherent_connection_bound_reads(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    request = {**parameters(), **cycle_fields(db)}
    traces = []
    connect = db._connect

    def traced_connect():
        conn = connect()
        trace = []
        conn.set_trace_callback(trace.append)
        traces.append((conn, trace))
        return conn

    monkeypatch.setattr(db, "_connect", traced_connect)
    ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(request), origin="planning_ui")
    assert len(traces) == 2, "One read snapshot and one publication/recheck transaction"
    for index, (conn, trace) in enumerate(traces):
        assert trace[0] == ("BEGIN" if index == 0 else "BEGIN IMMEDIATE")
        selects = [query for query in trace if query.lstrip().startswith("SELECT")]
        for table in ("activities AS a", "athlete_profile", "coach_constraints", "planning_checkpoints", "user_settings"):
            assert any(table in query for query in selects), table
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    assert not any("INSERT" in query or "UPDATE" in query for query in traces[0][1])
    assert traces[1][1][-1] == "COMMIT"


def test_read_snapshot_cannot_mix_a_concurrent_sync(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    started, done = Event(), Event()
    read_latest = db._get_latest_planning_checkpoint

    def after_first_read(conn):
        latest = read_latest(conn)
        started.set()
        assert done.wait(5), "Writer must commit while the old read snapshot is open"
        return latest

    def writer():
        assert started.wait(5)
        conn = db._connect()
        try:
            with conn:
                conn.execute("INSERT INTO activities(activity_id,date,sport,duration_minutes,tss) "
                             "VALUES ('synthetic-concurrent',?,'cycling',60,100)", (TODAY.isoformat(),))
                conn.execute("UPDATE athlete_profile SET ftp = 221")
        finally:
            conn.close()
            done.set()

    monkeypatch.setattr(db, "_get_latest_planning_checkpoint", after_first_read)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        captured = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(parameters()))
        future.result(timeout=5)
    monkeypatch.setattr(db, "_get_latest_planning_checkpoint", read_latest)
    current = ps._capture_plan_build_inputs(db, captured.parameters)
    assert len(captured.sources()["activities"]["data"]) == 28
    assert captured.sources()["athlete_profile"]["ftp"] == 220
    assert len(current.sources()["activities"]["data"]) == 29
    assert current.sources()["athlete_profile"]["ftp"] == 221
    assert captured.dependency_digest != current.dependency_digest


def test_frozen_calculation_never_reads_database_or_wall_clock(tmp_path, monkeypatch):
    from models import readiness

    db = seeded_db(tmp_path, rested=True)
    raw = parameters()
    snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw))
    before = snapshot.dependency_digest
    raw["events"][0]["date"] = "2030-01-01"
    raw["available_days"].clear()
    snapshot.sources()["athlete_profile"]["ftp"] = 999
    snapshot.parameters.as_dict()["events"].clear()
    assert snapshot.dependency_digest == before
    with pytest.raises(FrozenInstanceError):
        snapshot.revision_time = "changed"

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Calculation must use the captured inputs")

    class NoWallClock(datetime):
        now = staticmethod(forbidden)
        utcnow = staticmethod(forbidden)

    monkeypatch.setattr(db, "_connect", forbidden)
    monkeypatch.setattr(ps, "datetime", NoWallClock)
    monkeypatch.setattr(ps, "athlete_local_date", forbidden)
    monkeypatch.setattr(readiness, "athlete_local_date", forbidden)
    result = ps._calculate_plan_build(snapshot)
    assert json.loads(result.checkpoint_json)["goal_plan_snapshot"]["events"]
    assert json.loads(result.response_json)["plan_id"] is None
    with pytest.raises(FrozenInstanceError):
        result.checkpoint_json = "changed"


@pytest.mark.parametrize("direction", ["absent-to-null", "null-to-absent"])
def test_setting_row_presence_is_a_dependency(tmp_path, direction):
    db = seeded_db(tmp_path)
    key = "planning_profile"
    if direction == "absent-to-null":
        db.delete_user_setting(key)
    else:
        db.set_user_setting(key, None)
    before = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(parameters()))
    if direction == "absent-to-null":
        db.set_user_setting(key, None)
    else:
        db.delete_user_setting(key)
    after = ps._capture_plan_build_inputs(db, before.parameters)
    assert before.sources()["settings"] != after.sources()["settings"]
    assert before.dependency_digest != after.dependency_digest


@pytest.mark.parametrize("change", ["activity", "base", "day", "rule"])
def test_change_during_calculation_never_publishes_token(tmp_path, monkeypatch, change):
    db = seeded_db(tmp_path)
    before = protected_state(db)
    calculate = ps._calculate_plan_build

    def raced(snapshot):
        result = calculate(snapshot)
        if change == "activity":
            add_late_activity(db)
        elif change == "base":
            execute(db, "UPDATE planning_cycle_state SET revision=revision+1")
        elif change == "day":
            monkeypatch.setattr(ps, "athlete_local_date", lambda: TODAY + timedelta(days=1))
        else:
            monkeypatch.setattr(protocol, "PLANNING_BUILD_RULE_VERSION", "changed-test-rules")
        return result

    monkeypatch.setattr(ps, "_calculate_plan_build", raced)
    with pytest.raises(PlanningBuildPreviewError) as error:
        ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping({**parameters(), **cycle_fields(db)}), origin="planning_ui")
    assert error.value.code == "preview_stale"
    assert pending_count(db) == 0
    after = protected_state(db)
    assert after == before  # a lifecycle-only competing writer appended no checkpoint


@pytest.mark.parametrize(("change", "is_stale"), [
    ("insert_activity", True), ("update_activity", True), ("delete_activity", True),
    ("provider_link", True), ("profile", True), ("constraint", True), ("deactivate_constraint", True),
    ("demand", True), ("planning_profile", True), ("same_id_checkpoint", True),
    ("day", True), ("timezone", True), ("cutoff", True), ("rules", True),
    ("theme", False), ("hrv", False), ("old_activity", False),
    ("outside_constraint", False), ("identical_values", False),
])
def test_dependency_contract_includes_only_named_read_views(tmp_path, monkeypatch, change, is_stale):
    db = seeded_db(tmp_path, existing=True)
    snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(parameters()))
    if change == "insert_activity":
        add_late_activity(db)
    elif change == "update_activity":
        execute(db, "UPDATE activities SET tss = tss + 1 WHERE activity_id = 's0'")
    elif change == "delete_activity":
        execute(db, "DELETE FROM activities WHERE activity_id = 's0'")
    elif change == "provider_link":
        execute(db, "INSERT INTO activity_provider_links(canonical_activity_id,provider,provider_activity_id,"
                    "external_provider,external_id) VALUES ('s0','intervals','synthetic-link','garmin','linked')")
    elif change == "profile":
        execute(db, "UPDATE athlete_profile SET ftp = ftp + 1")
    elif change == "constraint":
        db.save_coach_constraint(date="2026-11-10", kind="forced_rest")
    elif change == "deactivate_constraint":
        db.deactivate_coach_constraint(1)
    elif change in {"demand", "planning_profile", "theme"}:
        key = {"demand": "planning_demand_level", "planning_profile": "planning_profile", "theme": "theme"}[change]
        db.set_user_setting(key, "changed")
    elif change == "same_id_checkpoint":
        stored = db.get_latest_planning_checkpoint()
        execute(db, "UPDATE planning_checkpoints SET checkpoint_data = ? WHERE id = ?",
                (json.dumps({**stored, "synthetic_change": True}), stored["id"]))
    elif change == "day":
        monkeypatch.setattr(ps, "athlete_local_date", lambda: TODAY + timedelta(days=1))
    elif change == "timezone":
        monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/London")
    elif change == "cutoff":
        monkeypatch.setattr(db, "_cutoff_date", lambda _days: "2026-07-19")
    elif change == "rules":
        monkeypatch.setattr(protocol, "PLANNING_BUILD_RULE_VERSION", "new-test-version")
    elif change == "hrv":
        db.save_hrv_data({TODAY.isoformat(): {"rmssd": 42}})
    elif change == "old_activity":
        db.save_activities([{"activity_id": "old", "date": "2026-01-01", "sport": "cycling", "tss": 100}])
    elif change == "outside_constraint":
        db.save_coach_constraint(date="2027-01-01", kind="forced_rest")
    else:
        execute(db, "UPDATE activities SET tss = tss WHERE activity_id = 's0'")
    current = ps._capture_plan_build_inputs(db, snapshot.parameters)
    assert (current.dependency_digest != snapshot.dependency_digest) is is_stale


def test_failure_before_storage_keeps_active_state_and_leaves_no_token(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    before = protected_state(db)

    def fail(*_args, **_kwargs):
        raise ArithmeticError("synthetic forecast failure")

    monkeypatch.setattr(ps, "_forecast", fail)
    with pytest.raises(ArithmeticError, match="synthetic"):
        ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping({**parameters(), **cycle_fields(db)}), origin="planning_ui")
    assert protected_state(db) == before
    assert pending_count(db) == 0


def test_nonfinite_source_is_not_turned_into_a_plausible_preview(tmp_path):
    db = seeded_db(tmp_path)
    execute(db, "UPDATE activities SET tss = ? WHERE activity_id = 's0'", (float("inf"),))
    before = protected_state(db)
    with pytest.raises(ValueError):
        ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping({**parameters(), **cycle_fields(db)}), origin="planning_ui")
    assert protected_state(db) == before
    assert pending_count(db) == 0


@pytest.mark.parametrize("origin", ["planning_ui", "coach"])
def test_retained_settings_are_normalized_intentions_not_live_writes(tmp_path, origin):
    db = seeded_db(tmp_path)
    before = protected_state(db)
    request = parameters()
    request["demand"] = None
    shown = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping({**request, **cycle_fields(db)}), origin=origin)
    retained = get_preview(db, shown["confirmation"]["preview_id"], origin=origin)
    writes = json.loads(retained["settings_write_json"])
    assert ("planning_profile" in writes) is (origin == "planning_ui")
    assert ("planning_demand_level" in writes) is (origin == "planning_ui")
    assert shown["parameters"]["demand"] == "moderate"
    assert protected_state(db) == before
    context = json.loads(retained["dependency_context_json"])
    assert context["components"]["activities"]
    assert "s0" not in retained["dependency_context_json"]  # hashes/bounds only, no duplicated source history

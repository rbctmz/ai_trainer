"""Explicit synthetic plan seeding; never a public runtime persistence flag."""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from uuid import uuid4


def pin_day(monkeypatch, day):
    """Explicit athlete day for a historical mutation scenario."""
    from tests.smoke._planning_cycle_regressions import pin_clock
    pin_clock(monkeypatch, observed=datetime(day.year, day.month, day.day, 9, tzinfo=timezone.utc))


def write_context(db):
    from data.planning_cycle_writes import write_token
    return write_token(db.planning_write_context())


def restore_fields(db):
    context = db.planning_write_context()
    return {"expected_cycle_id": context["cycle_id"], "expected_cycle_revision": context["cycle_revision"],
            "expected_selection_revision": context["selection_revision"]}


def append_history(db, checkpoint):
    """Fixture-only unassigned history, deliberately not selected."""
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        saved = db._insert_planning_checkpoint(conn, checkpoint)
        conn.commit()
        return saved
    finally:
        conn.close()


def seed_checkpoint(db, checkpoint):
    """Create an explicit synthetic legacy cycle/version for pre-S2 tests.

    Tests choose this setup operation. Production never infers membership of
    old history or lets a raw save select/reopen a cycle.
    """
    from data.planning_cycles import PlanningCycleStore
    from models.planning_cycle import checkpoint_period
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        store = PlanningCycleStore(conn)
        state = store.state()
        saved = db._insert_planning_checkpoint(conn, checkpoint)
        period = checkpoint_period(checkpoint)
        start = period.start.isoformat() if period.start else None
        end = period.end.isoformat() if period.end else None
        cycle_id = state["current_cycle_id"]
        if cycle_id is None:
            cycle_id = str(uuid4())
            conn.execute("INSERT INTO planning_cycles(id,current_checkpoint_id,revision,status,start_date,end_date,origin) VALUES(?,?,1,'open',?,?,'legacy_import')", (cycle_id, saved["id"], start, end))
            conn.execute("UPDATE planning_cycle_state SET current_cycle_id=?,revision=revision+1 WHERE id=1", (cycle_id,))
        else:
            conn.execute("UPDATE planning_cycles SET current_checkpoint_id=?,revision=revision+1,start_date=?,end_date=? WHERE id=?", (saved["id"], start, end, cycle_id))
        conn.execute("INSERT INTO planning_cycle_versions VALUES(?,?,'adjustment')", (saved["id"], cycle_id))
        conn.commit()
        return saved
    finally:
        conn.close()


def build_plan(db, **kwargs):
    """Seed the original v1 calculation, preserving complete golden payloads."""
    from api import planning_service as ps
    from models.planning_build_confirmation import BuildParameters
    bound = inspect.signature(ps.build_plan).bind(db, **kwargs)
    bound.apply_defaults()
    values = bound.arguments
    parameters = {key: value for key, value in values.items()
                  if key not in {"db", "persist", "expected_base_checkpoint_id", "checkpoint_source", "cycle_context"}}
    parameters["base_checkpoint_id"] = values["expected_base_checkpoint_id"]
    snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(parameters), checkpoint_source=values["checkpoint_source"])
    prepared = ps._calculate_plan_build(snapshot)
    response = json.loads(prepared.response_json)
    if values["persist"]:
        if values["demand"] is not None:
            db.set_user_setting(ps.PLANNING_DEMAND_SETTING_KEY, snapshot.parameters.as_dict()["demand"])
        saved = seed_checkpoint(db, json.loads(prepared.checkpoint_json))
        response.update(plan_id=str(saved["id"]), confirmation_required=False)
    return response

"""M4c public build, effective dose and atomic publication on synthetic SQLite."""

from copy import deepcopy
from datetime import date, timedelta
import json

import pytest

from api import planning_service as ps
from models.planning_build_confirmation import (
    BuildParameters,
    PlanningBuildPreviewError,
)
from models.planning_entry_publication import (
    assess_entry_assignments,
    entry_base,
    execution_partition,
    entry_validation_context,
)
from tests.smoke._planning_build_confirmation import pin_clock
from tests.smoke._planning_entry_dose import exposure_db, entry_request
from tests.smoke.test_planning_entry_capture_m4b import all_tables

CAPS = {
    sport: {
        "source": "athlete_declared",
        "weekly_minutes": minutes,
        "weekly_sessions": 1,
        "max_session_minutes": minutes,
    }
    for sport, minutes in (("bike", 60), ("run", 40), ("swim", 20))
}


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    pin_clock(monkeypatch)
    db = exposure_db(tmp_path, ["running"] * 4)
    raw = entry_request(db, limits=deepcopy(CAPS))
    return db, raw


def prepared(db, raw):
    return ps._calculate_plan_build(
        ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw))
    )


def assessment(result):
    return json.loads(result.response_json)["entry_load"]


@pytest.mark.parametrize("start", ["2026-10-26", "2026-10-28"])
def test_explicit_limits_produce_usable_initial_plan_and_exact_cycle_anchor(
    scenario, start
):
    db, raw = scenario
    raw.update(start_date=start, start_week="2026-10-26")
    before = all_tables(db)
    candidate = prepared(db, raw)
    entry = assessment(candidate)
    assert entry["status"] == "supported", entry["blockers"]
    assert entry["scope"] == {
        "start_date": start,
        "end_date": (date.fromisoformat(start) + timedelta(days=13)).isoformat(),
    }
    assert json.loads(candidate.response_json)["build_readiness"]["status"] == "ready"
    assert all_tables(db) == before
    shown = ps.prepare_plan_build(
        db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui"
    )
    saved = ps.confirm_plan_build(
        db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui"
    )
    assert saved["entry_load"] == entry
    assert saved["entry_load"]["can_publish"] is True
    frozen = all_tables(db)
    replay = ps.confirm_plan_build(
        db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui"
    )
    assert replay["confirmation"]["replayed"] is True
    assert all_tables(db) == frozen


@pytest.mark.parametrize("origin", ["planning_ui", "coach"])
def test_missing_discipline_baseline_refuses_before_any_table_write(scenario, origin):
    db, raw = scenario
    raw.pop("initial_dose_limits")
    before = all_tables(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        ps.prepare_plan_build(
            db, parameters=BuildParameters.from_mapping(raw), origin=origin
        )
    assert error.value.code == "entry_dose_required" and error.value.status == 422
    assert {b["sport"] for b in error.value.context["entry_load"]["blockers"]} >= {
        "bike",
        "swim",
    }
    assert all_tables(db) == before


def test_impossible_small_catalog_dose_is_honest_no_token(scenario):
    db, raw = scenario
    raw["initial_dose_limits"]["swim"].update(weekly_minutes=1, max_session_minutes=1)
    before = all_tables(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        ps.prepare_plan_build(
            db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui"
        )
    assert error.value.code == "entry_dose_infeasible"
    assert error.value.context["entry_load"]["can_publish"] is False
    assert all_tables(db) == before


def test_final_validator_finds_overdose_even_with_catalog_and_m3_ready(scenario):
    db, raw = scenario
    candidate = prepared(db, raw)
    plan = json.loads(candidate.checkpoint_json)["goal_plan_snapshot"]
    template = next(t for t in plan["session_templates"] if t.get("sessions"))
    template["sessions"][0]["duration_minutes"] = 999
    context = entry_validation_context(plan, candidate.snapshot.context())
    result = assess_entry_assignments(
        plan,
        entry_base(context, candidate.snapshot.parameters.as_dict()),
        execution_partition(context),
        context=context,
    )
    assert result["status"] == "blocked"
    assert "entry_session_exceeded" in {b["code"] for b in result["blockers"]}


def test_legacy_low_level_calculation_is_not_promoted_to_publishable_entry(scenario):
    db, raw = scenario
    for key in (
        "action",
        "base_cycle_id",
        "base_cycle_revision",
        "base_selection_revision",
        "replace_current_cycle",
        "start_date",
    ):
        raw.pop(key, None)
    assert json.loads(prepared(db, raw).response_json).get("entry_load") is None


def test_same_frozen_calculation_does_not_read_storage_or_clock(scenario, monkeypatch):
    db, raw = scenario
    snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw))
    before = ps._calculate_plan_build(snapshot)

    def forbidden(*args, **kwargs):
        raise AssertionError("frozen entry calculation accessed live inputs")

    monkeypatch.setattr(db, "_connect", forbidden)
    monkeypatch.setattr(ps, "athlete_local_date", forbidden)
    after = ps._calculate_plan_build(snapshot)
    assert before == after

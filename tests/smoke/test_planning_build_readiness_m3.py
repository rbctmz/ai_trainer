"""S3 M3: final candidate invariants and shared atomic publication guard."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
import json

import pytest

from api import planning_service as ps
from data import planning_build_preview_store as store
from models.planning_build_confirmation import (
    BuildParameters,
    canonical_json,
    PlanningBuildPreviewError,
)
from models.planning_build_readiness import (
    assess_plan_build_readiness,
    effective_build_totals,
)
from tests.smoke._planning_build_confirmation import (
    seeded_db,
    parameters,
    cycle_fields,
    pin_clock,
)


def request(db):
    return {
        **parameters(),
        **cycle_fields(db),
        "events": [],
        "start_week": "2026-10-26",
        "start_date": "2026-10-26",
    }


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    pin_clock(monkeypatch)
    db = seeded_db(tmp_path, rested=True)
    snapshot = ps._capture_plan_build_inputs(
        db, BuildParameters.from_mapping(request(db))
    )
    prepared = ps._calculate_plan_build(snapshot)
    return (
        db,
        prepared,
        json.loads(prepared.checkpoint_json)["goal_plan_snapshot"],
        json.loads(prepared.response_json),
        {
            **snapshot.context(),
            "parameters": snapshot.parameters.as_dict(),
        },
    )


def assess(candidate):
    _, _, plan, response, context = candidate
    return assess_plan_build_readiness(plan, response, context)


def single(plan, sport="bike"):
    return next(
        s
        for d in plan["session_templates"]
        for s in d.get("sessions", [])
        if s.get("sport") == sport
    )


def composite(plan):
    return next(
        s
        for d in plan["session_templates"]
        for s in d.get("sessions", [])
        if s.get("kind") == "composite"
    )


def state(db):
    conn = db._connect()
    try:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        return {
            name: conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
            for name in names
        }
    finally:
        conn.close()


def refresh(plan, response, context):
    assessment = assess_plan_build_readiness(plan, response, context)
    plan["build_readiness"] = response["build_readiness"] = assessment
    return assessment


def test_complete_final_candidate_is_ready_pure_and_deterministic(candidate):
    before = deepcopy(candidate[2:])
    result = assess(candidate)
    assert result["status"] == "ready", result["blockers"]
    assert result["can_confirm"] is True
    assert result["training_suitability"] == "not_assessed"
    assert result["assessed_session_count"] > 0
    assert assess(candidate) == result
    assert candidate[2:] == before


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("missing_steps", "prescription_missing"),
        ("failed_bounds", "prescription_infeasible"),
        ("unknown_status", "prescription_infeasible"),
        ("parameter_tss", "load_inconsistent"),
        ("step_tss", "load_inconsistent"),
        ("derived_tss", "load_inconsistent"),
        ("step_seconds", "duration_inconsistent"),
        ("range", "target_semantics_unverified"),
        ("unit", "target_semantics_unverified"),
        ("provenance", "target_semantics_unverified"),
        ("nan", "target_semantics_unverified"),
        ("rpe_policy", "target_semantics_unverified"),
        ("rpe_recovery", "target_semantics_unverified"),
        ("zero_exercise", "prescription_infeasible"),
    ],
)
def test_single_and_target_corruption_is_blocked_with_session_address(
    candidate, mutation, code
):
    plan = candidate[2]
    session = single(plan, "swim" if mutation.startswith("rpe") else "bike")
    if mutation == "missing_steps":
        session["materialized_steps"] = []
    elif mutation == "failed_bounds":
        session["failed_bounds"] = ["density_below_minimum"]
    elif mutation == "unknown_status":
        session["materialization_status"] = "unknown"
    elif mutation == "parameter_tss":
        session["parameter_snapshot"]["target_tss"] += 2
    elif mutation == "step_tss":
        session["materialized_steps"][0]["tss"] += 2
    elif mutation == "derived_tss":
        session["parameter_snapshot"]["planned_tss_evidence"]["planned_tss"] += 2
    elif mutation == "step_seconds":
        session["materialized_steps"][0]["duration_seconds"] += 60
    elif mutation == "range":
        session["materialized_steps"][0]["target"].update(low=200, high=1)
    elif mutation == "unit":
        session["materialized_steps"][0]["target"]["unit"] = "bpm"
    elif mutation == "provenance":
        session["target_provenance"]["value"] = None
    elif mutation == "nan":
        session["materialized_steps"][0]["target"]["low"] = float("nan")
    elif mutation == "rpe_policy":
        session["definition_snapshot"]["rpe_stage_targets"] = []
    elif mutation == "rpe_recovery":
        session["materialized_steps"][0]["target"].update(low=6, high=8)
    elif mutation == "zero_exercise":
        session["total_tss"] = session["parameter_snapshot"]["target_tss"] = 0
        for step in session["materialized_steps"]:
            step["tss"] = 0
    result = assess(candidate)
    assert result["status"] == "blocked"
    assert any(
        b["code"] == code and b["session_id"] == session["session_id"]
        for b in result["blockers"]
    ), result
    canonical_json(result)


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("bad_leg", "prescription_infeasible"),
        ("missing_leg", "prescription_missing"),
        ("leg_status", "prescription_infeasible"),
        ("transition", "duration_inconsistent"),
        ("parent_tss", "load_inconsistent"),
        ("leg_tss", "load_inconsistent"),
    ],
)
def test_composite_checks_legs_and_exact_transition(candidate, mutation, code):
    parent = composite(candidate[2])
    if mutation == "bad_leg":
        parent["legs"][1]["failed_bounds"] = ["density_below_minimum"]
    elif mutation == "missing_leg":
        parent["legs"] = []
    elif mutation == "leg_status":
        parent["legs"][1]["materialization_status"] = "unknown"
    elif mutation == "transition":
        parent.pop("transition_minutes")
    elif mutation == "parent_tss":
        parent["parameter_snapshot"]["target_tss"] += 2
    elif mutation == "leg_tss":
        parent["legs"][1]["target_tss"] += 2
    blockers = assess(candidate)["blockers"]
    assert any(
        b["code"] == code and b["session_id"] == parent["session_id"] for b in blockers
    ), blockers
    if mutation == "bad_leg":
        assert any(b["leg_index"] == 2 for b in blockers)


@pytest.mark.parametrize(
    "field",
    [
        "day",
        "parts",
        "week",
        "sport",
        "weekly_array",
        "response_total",
        "response_week",
        "forecast",
    ],
)
def test_each_final_aggregate_and_forecast_input_is_checked(candidate, field):
    plan, response = candidate[2:4]
    if field == "day":
        plan["daily_plan"][0]["total_tss"] += 2
    elif field == "parts":
        plan["daily_plan"][0]["parts"]["bike"] += 2
    elif field == "week":
        plan["weekly_summary"][0]["weekly_tss"] += 2
    elif field == "sport":
        plan["weekly_summary"][0]["bike"] += 2
    elif field == "weekly_array":
        plan["weekly_tss_plan"][0] += 2
    elif field == "response_total":
        response["totals"]["total_tss"] += 2
    elif field == "response_week":
        response["weeks"][0]["swim"] += 2
    elif field == "forecast":
        plan["forecast_input"]["daily_loads"][0]["total_tss"] += 2
    assert any(b["code"] == "load_inconsistent" for b in assess(candidate)["blockers"])


def test_availability_is_final_minutes_and_declared_days(candidate):
    candidate[4]["parameters"]["available_hours"] = 0.1
    candidate[4]["parameters"]["available_days"] = ["sun"]
    assert any(
        b["code"] == "availability_exceeded" for b in assess(candidate)["blockers"]
    )


def test_last_day_included_and_past_legacy_preserved(candidate):
    plan, response, context = candidate[2:]
    last = max(day["date"] for day in plan["session_templates"] if day.get("sessions"))
    context["athlete_day"] = last
    # Past history is not a newly assigned session and cannot block on legacy structure.
    first = next(day for day in plan["session_templates"] if day.get("sessions"))
    first["sessions"][0]["materialization_status"] = "legacy_role_fallback"
    last_day = next(day for day in plan["session_templates"] if day["date"] == last)
    last_day["sessions"][0]["materialization_status"] = "infeasible"
    blockers = assess(candidate)["blockers"]
    assert any(
        b["code"] == "prescription_infeasible" and b["date"] == last for b in blockers
    )
    assert not any(b["date"] == first["date"] for b in blockers)


def test_budget_and_allocated_parts_are_not_asserted_equal_to_effective_tss(candidate):
    session = single(candidate[2])
    session["parameter_snapshot"]["requested_tss"] = 999
    candidate[2]["base_weekly_tss_plan"] = [999] * len(candidate[2]["weekly_tss_plan"])
    assert assess(candidate)["status"] == "ready"


def test_whole_plan_rounds_raw_sum_once_and_primary_minutes_not_summed_twice():
    plan = {
        "daily_plan": [(date(2026, 10, 26), 1.4, {}), (date(2026, 11, 2), 1.4, {})],
        "weekly_summary": [{"week_start": "2026-10-26"}, {"week_start": "2026-11-02"}],
    }
    assert effective_build_totals(plan) == {"total_tss": 3, "peak_tss": 1}


@pytest.mark.parametrize("origin", ["planning_ui", "coach"])
def test_both_origins_ready_prepare_confirm_and_replay_are_exact(candidate, origin):
    db, _, _, _, _ = candidate
    shown = ps.prepare_plan_build(
        db, parameters=BuildParameters.from_mapping(request(db)), origin=origin
    )
    proposal_id = None
    if origin == "coach":
        from tests.smoke.test_planning_build_coach_confirmation import save

        proposal_id = save(db, shown)["id"]
    token = shown["confirmation"]["preview_id"]
    before = store.get_preview(db, token, origin=origin)
    result = ps.confirm_plan_build(
        db, preview_id=token, origin=origin, proposal_id=proposal_id
    )
    assert result["build_readiness"] == shown["build_readiness"]
    assert (
        json.loads(before["checkpoint_json"])["goal_plan_snapshot"]["build_readiness"]
        == result["build_readiness"]
    )
    saved = state(db)
    replay = ps.confirm_plan_build(
        db, preview_id=token, origin=origin, proposal_id=proposal_id
    )
    assert replay["confirmation"]["replayed"]
    assert state(db) == saved


@pytest.mark.parametrize("origin", ["planning_ui", "coach"])
def test_blocked_prepare_has_no_token_or_any_table_write(
    candidate, monkeypatch, origin
):
    db, prepared, plan, response, context = candidate
    single(plan)["materialized_steps"] = []
    refresh(plan, response, context)
    checkpoint = json.loads(prepared.checkpoint_json)
    checkpoint["goal_plan_snapshot"] = plan
    invalid = replace(
        prepared,
        checkpoint_json=canonical_json(checkpoint),
        response_json=canonical_json(response),
    )
    monkeypatch.setattr(ps, "_calculate_plan_build", lambda _: invalid)
    before = state(db)
    with pytest.raises(PlanningBuildPreviewError) as exc:
        ps.prepare_plan_build(
            db, parameters=BuildParameters.from_mapping(request(db)), origin=origin
        )
    assert (exc.value.status, exc.value.code) == (422, "plan_not_ready")
    assert exc.value.context["build_readiness"]["status"] == "blocked"
    assert state(db) == before


@pytest.mark.parametrize(
    "corruption,code,status",
    [
        ("blocked", "plan_not_ready", 409),
        ("false_ready", "preview_corrupt", 500),
        ("fingerprint", "preview_corrupt", 500),
        ("missing", "preview_required", 409),
        ("header", "preview_corrupt", 500),
        ("malformed", "preview_corrupt", 500),
    ],
)
@pytest.mark.parametrize("origin", ["planning_ui", "coach"])
def test_retained_candidate_guard_before_writes(
    candidate, corruption, code, status, origin
):
    db = candidate[0]
    shown = ps.prepare_plan_build(
        db, parameters=BuildParameters.from_mapping(request(db)), origin=origin
    )
    proposal_id = None
    if origin == "coach":
        from tests.smoke.test_planning_build_coach_confirmation import save

        proposal_id = save(db, shown)["id"]
    token = shown["confirmation"]["preview_id"]
    row = store.get_preview(db, token, origin=origin)
    checkpoint, response = (
        json.loads(row["checkpoint_json"]),
        json.loads(row["response_json"]),
    )
    plan = checkpoint["goal_plan_snapshot"]
    context = {
        **json.loads(row["dependency_context_json"]),
        "parameters": json.loads(row["parameters_json"]),
    }
    if corruption in {"blocked", "false_ready"}:
        single(plan)["materialized_steps"] = []
        if corruption == "blocked":
            refresh(plan, response, context)
    elif corruption == "fingerprint":
        plan["build_readiness"]["candidate_fingerprint"] = "wrong"
    elif corruption == "missing":
        plan.pop("build_readiness")
        response.pop("build_readiness")
    elif corruption == "header":
        checkpoint["total_tss"] += 5
    elif corruption == "malformed":
        plan["build_readiness"] = {"status": "ready"}
    row.update(
        checkpoint_json=canonical_json(checkpoint),
        response_json=canonical_json(response),
    )
    conn = db._connect()
    try:
        with conn:
            conn.execute(
                "UPDATE planning_build_previews SET checkpoint_json=?,response_json=?,payload_digest=? WHERE preview_id=?",
                (
                    row["checkpoint_json"],
                    row["response_json"],
                    store._payload_digest(row),
                    token,
                ),
            )
    finally:
        conn.close()
    before = state(db)
    with pytest.raises(PlanningBuildPreviewError) as exc:
        ps.confirm_plan_build(
            db, preview_id=token, origin=origin, proposal_id=proposal_id
        )
    assert (exc.value.code, exc.value.status) == (code, status)
    assert state(db) == before


def test_recovery_large_budget_is_explicitly_capped_to_light_catalog_dose():
    from models.workout_catalog import materialize_session_template

    session = materialize_session_template(
        phase="Recovery",
        session_role="long",
        sport="bike",
        goal_type="triathlon",
        target_tss=46.6,
        estimated_duration_minutes=115,
        load_state="deep_fatigue",
        zone_snapshot={},
    )
    assert session["materialization_status"] == "materialized"
    assert session["session_role"] == "recovery"
    assert session["parameter_snapshot"]["target_tss"] <= 46.6
    assert session["duration_minutes"] <= 115
    assert session["selection_evidence"]["requested_tss"] == 46.6
    assert session["selection_evidence"]["replacement_requested_tss"] < 46.6
    assert max(session["fatigue_cost"]) <= 1


def test_bike_activation_uses_prescription_load_not_its_requested_budget():
    from models.workout_catalog import (
        catalog_definitions,
        materialize_workout,
        planned_bike_tss_from_steps,
    )

    definition = next(
        d for d in catalog_definitions() if d.template_key == "bike_activation"
    )
    workout = materialize_workout(
        definition, {"duration_minutes": 20, "target_tss": 24}, {"ftp": 220}
    )
    derived = planned_bike_tss_from_steps(
        workout["steps"], workout["target_provenance"]
    )
    assert workout["parameter_snapshot"]["target_tss"] == derived["planned_tss"]
    assert workout["parameter_snapshot"]["requested_tss"] == 24
    assert (
        workout["parameter_snapshot"]["planned_tss_method"] == "prescription_np_tss_v1"
    )


def test_http_blocked_plan_has_typed_reasons_and_no_token_or_writes(candidate):
    from api.planning_build_contract import BuildReadinessError
    from tests.smoke._planning_cycle_regressions import client_for

    db = candidate[0]
    before = state(db)
    # Sunday A prescribes an activation on an unallocated off slot: a real
    # incomplete candidate, retained as a refusal rather than hidden as rest.
    body = {
        **request(db),
        "planning_mode": "event_goal",
        "available_hours": 10,
        "events": [
            {
                "date": "2027-02-14",
                "priority": "A",
                "confirmed": True,
                "label": "Synthetic A",
            }
        ],
    }
    with client_for(db) as client:
        res = client.post("/api/planning/build", json=body)
    assert res.status_code == 422, res.text
    error = BuildReadinessError.model_validate(res.json())
    assert error.build_readiness.status == "blocked"
    assert all(
        key not in res.json() for key in ("preview_id", "confirmation", "plan_id")
    )
    assert state(db) == before


def test_16_week_valid_candidate_prepares_and_confirms_with_bounded_validation(
    candidate,
):
    import time

    db = candidate[0]
    body = {
        **request(db),
        "planning_mode": "event_goal",
        "available_hours": 10,
        "events": [
            {
                "date": "2027-02-13",
                "priority": "A",
                "confirmed": True,
                "label": "Synthetic A",
            }
        ],
    }
    start = time.perf_counter()
    shown = ps.prepare_plan_build(
        db, parameters=BuildParameters.from_mapping(body), origin="planning_ui"
    )
    prepare_seconds = time.perf_counter() - start
    assert len(shown["weeks"]) == 16
    row = store.get_preview(
        db, shown["confirmation"]["preview_id"], origin="planning_ui"
    )
    plan = json.loads(row["checkpoint_json"])["goal_plan_snapshot"]
    race = next(
        item for item in plan["forecast_input"]["daily_loads"] if item["race_tss"] > 0
    )
    assert race["planned_tss"] == 0 and race["total_tss"] == race["race_tss"]
    assert shown["totals"] == effective_build_totals(plan)
    assert shown["build_readiness"]["status"] == "ready"
    assert prepare_seconds < 10
    start = time.perf_counter()
    applied = ps.confirm_plan_build(
        db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui"
    )
    assert time.perf_counter() - start < 10
    assert applied["build_readiness"] == shown["build_readiness"]


def test_primary_day_projection_cannot_disagree_with_assigned_session(candidate):
    day = next(d for d in candidate[2]["session_templates"] if d.get("sessions"))
    day["materialization_status"] = "infeasible"
    assert any(
        b["field"] == "primary.materialization_status"
        for b in assess(candidate)["blockers"]
    )


def test_false_ready_prepare_is_corrupt_without_any_write(candidate, monkeypatch):
    db, prepared, plan, response, _ = candidate
    single(plan)["materialized_steps"] = []
    checkpoint = json.loads(prepared.checkpoint_json)
    checkpoint["goal_plan_snapshot"] = plan
    corrupt = replace(prepared, checkpoint_json=canonical_json(checkpoint))
    monkeypatch.setattr(ps, "_calculate_plan_build", lambda _: corrupt)
    before = state(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        ps.prepare_plan_build(
            db,
            parameters=BuildParameters.from_mapping(request(db)),
            origin="planning_ui",
        )
    assert (error.value.code, error.value.status) == ("preview_corrupt", 500)
    assert state(db) == before


def test_old_applied_receipt_without_assessment_replays_unchanged_before_new_guard(
    candidate, monkeypatch
):
    from models import planning_build_readiness as readiness
    from tests.smoke._planning_cycle_regressions import client_for

    db = candidate[0]
    shown = ps.prepare_plan_build(
        db, parameters=BuildParameters.from_mapping(request(db)), origin="planning_ui"
    )
    token = shown["confirmation"]["preview_id"]
    applied = ps.confirm_plan_build(db, preview_id=token, origin="planning_ui")
    row = store.get_preview(db, token, origin="planning_ui")
    cp, response = json.loads(row["checkpoint_json"]), json.loads(row["response_json"])
    cp["goal_plan_snapshot"].pop("build_readiness")
    response.pop("build_readiness")
    applied.pop("build_readiness")
    row.update(
        checkpoint_json=canonical_json(cp),
        response_json=canonical_json(response),
        applied_response_json=canonical_json(applied),
    )
    row["payload_digest"] = store._payload_digest(row)
    conn = db._connect()
    try:
        with conn:
            conn.execute(
                "UPDATE planning_build_previews SET checkpoint_json=?,response_json=?,applied_response_json=?,payload_digest=?,receipt_digest=? WHERE preview_id=?",
                (
                    row["checkpoint_json"],
                    row["response_json"],
                    row["applied_response_json"],
                    row["payload_digest"],
                    store._receipt_digest(row),
                    token,
                ),
            )
            conn.execute(
                "UPDATE planning_checkpoints SET checkpoint_data=? WHERE id=?",
                (row["checkpoint_json"], row["applied_checkpoint_id"]),
            )
    finally:
        conn.close()

    def forbidden(*_a, **_k):
        raise AssertionError("Applied receipt must not be reassessed")

    monkeypatch.setattr(readiness, "assess_plan_build_readiness", forbidden)
    # PinnedDateTime is a test subclass; restore parsing type for the GET reader
    # while athlete-day helpers remain pinned. No production clock defect inferred.
    from datetime import datetime

    monkeypatch.setattr(ps, "datetime", datetime)
    before = state(db)
    with client_for(db) as client:
        replay = client.post(
            "/api/planning/build/confirm", json={"preview_id": token, "confirm": True}
        )
        overview = client.get("/api/planning/overview")
    assert replay.status_code == 200, replay.text
    assert "build_readiness" not in replay.json()
    assert replay.json() == {
        **applied,
        "confirmation": {**applied["confirmation"], "replayed": True},
    }
    assert overview.status_code == 200
    assert overview.json()["build_readiness"]["status"] == "unassessed"
    assert state(db) == before


def test_non_build_checkpoint_does_not_inherit_a_stale_ready_assessment(candidate):
    from models.planning_checkpoints import (
        build_planning_checkpoint,
        restore_goal_plan_from_checkpoint,
    )

    restored = restore_goal_plan_from_checkpoint({"goal_plan_snapshot": candidate[2]})
    rebuilt = build_planning_checkpoint(restored)
    assert "build_readiness" not in rebuilt["goal_plan_snapshot"]
    assert "forecast_input" not in rebuilt["goal_plan_snapshot"]


@pytest.mark.parametrize(
    "mutation",
    ["policy_unused_stage", "absolute_fraction", "unknown_kind", "empty_calendar"],
)
def test_semantic_and_shape_boundaries_fail_closed(candidate, mutation):
    plan = candidate[2]
    if mutation == "policy_unused_stage":
        session = single(plan, "swim")
        session["definition_snapshot"]["rpe_stage_targets"][-1] = ["work", 1, 11]
    elif mutation == "absolute_fraction":
        single(plan)["target_provenance"]["value"] = 999
    elif mutation == "unknown_kind":
        single(plan)["kind"] = "unknown"
    elif mutation == "empty_calendar":
        plan["daily_plan"] = []
        plan["session_templates"] = []
    result = assess(candidate)
    assert result["status"] == "blocked"


def test_load_provenance_separates_power_estimates_and_composite_aggregation(candidate):
    assert single(candidate[2], "bike")["load_provenance"]["status"] == "derived"
    for sport in ("run", "swim"):
        assert single(candidate[2], sport)["load_provenance"] == {
            "method": "catalog_budget_estimate_v1",
            "status": "estimated",
            "source": "catalog_tss_budget",
        }
    assert composite(candidate[2])["load_provenance"]["method"] == "sum_leg_tss_v1"


@pytest.mark.parametrize(
    "mutation",
    [
        "session_id",
        "leg_id",
        "catalog_policy",
        "duplicate_week",
        "numeric_string_duration",
    ],
)
def test_identity_catalog_calendar_and_bounded_power_validation(candidate, mutation):
    plan, response = candidate[2:4]
    if mutation == "session_id":
        single(plan)["session_id"] = ""
    elif mutation == "leg_id":
        composite(plan)["legs"][0]["leg_id"] = composite(plan)["session_id"]
    elif mutation == "catalog_policy":
        leaf = single(plan, "swim")
        leaf["definition_snapshot"]["rpe_stage_targets"] = [
            [key, 6, 8]
            for key, _, _ in leaf["definition_snapshot"]["rpe_stage_targets"]
        ]
        for step in leaf["materialized_steps"]:
            step["target"].update(low=6, high=8)
    elif mutation == "duplicate_week":
        plan["weekly_summary"].append(deepcopy(plan["weekly_summary"][-1]))
        plan["weekly_tss_plan"].append(plan["weekly_tss_plan"][-1])
        response["weeks"].append(deepcopy(response["weeks"][-1]))
    elif mutation == "numeric_string_duration":
        single(plan)["materialized_steps"][0]["duration_seconds"] = "99999999999999"
    assert assess(candidate)["status"] == "blocked"


def resync_candidate(candidate):
    """Keep arithmetic honest so semantic regressions isolate catalog eligibility."""
    from models.planning_build_readiness import normalize_build_loads, forecast_build_input
    from models.planning_build_confirmation import fingerprint

    plan, response, context = candidate[2:]
    for day in plan["session_templates"]:
        if day.get("sessions"):
            primary = day["sessions"][0]
            for field in ("sport", "legs", "materialized_steps", "target_provenance", "parameter_snapshot", "duration_minutes", "total_tss"):
                if field in primary:
                    day[field] = deepcopy(primary[field])
    plan["daily_plan"] = [(d["date"], d["total_tss"], d["parts"]) for d in plan["daily_plan"]]
    normalized = normalize_build_loads(plan, context)
    plan.clear()
    plan.update(normalized)
    plan["daily_plan"] = [{"date": d, "total_tss": t, "parts": p} for d, t, p in plan["daily_plan"]]
    response["weeks"] = ps._weeks_payload(plan["weekly_summary"], plan["phases"])
    response["totals"].update(effective_build_totals(plan))
    preview = response["preview"]
    preview["total_tss_after"] = response["totals"]["total_tss"]
    preview["weekly_tss_delta"] = round(preview["total_tss_after"] - preview["total_tss_before"])
    preview["weekly_tss_after"] = plan["weekly_tss_plan"]
    plan["forecast_input"] = forecast_build_input(plan, context, plan["forecast_input"]["initial_metrics"])
    response["forecast"]["input_fingerprint"] = fingerprint(plan["forecast_input"])


@pytest.mark.parametrize("leg", [False, True])
def test_catalog_sport_mismatch_is_blocked_even_with_consistent_aggregates(candidate, leg):
    row = composite(candidate[2])["legs"][0] if leg else single(candidate[2])
    row["sport"] = "run"
    resync_candidate(candidate)
    result = assess(candidate)
    assert result["status"] == "blocked", result
    assert any(b["code"] == "prescription_infeasible" and b["field"].endswith("definition_snapshot") for b in result["blockers"]), result


def test_target_method_must_be_supported_by_selected_definition(candidate):
    row = single(candidate[2])
    row["target_provenance"] = {"kind": "css", "source": "athlete_profile.css", "value": 110}
    for step in row["materialized_steps"]:
        old = step["target"]
        step["target"] = {"type": "pace", "unit": "seconds_per_100m", "fast": round(110 / old["relative_high"], 1), "slow": round(110 / old["relative_low"], 1), "relative_low": old["relative_low"], "relative_high": old["relative_high"]}
    for key in ("planned_tss", "planned_tss_method", "planned_tss_evidence"):
        row["parameter_snapshot"].pop(key, None)
    resync_candidate(candidate)
    result = assess(candidate)
    assert result["status"] == "blocked", result
    assert any(b["code"] == "target_semantics_unverified" for b in result["blockers"]), result


@pytest.mark.parametrize("mutation", ["missing_run", "reversed"])
def test_composite_requires_catalog_sports_in_order_even_after_resumming(candidate, mutation):
    row = composite(candidate[2])
    row["legs"] = row["legs"][:1] if mutation == "missing_run" else list(reversed(row["legs"]))
    for index, leg in enumerate(row["legs"], 1):
        leg["leg_index"] = index
    row["total_tss"] = round(sum(leg["target_tss"] for leg in row["legs"]), 1)
    row["duration_minutes"] = sum(leg["duration_minutes"] for leg in row["legs"]) + row["transition_minutes"]
    row["parameter_snapshot"]["target_tss"] = row["total_tss"]
    row["parameter_snapshot"]["duration_minutes"] = row["duration_minutes"]
    resync_candidate(candidate)
    result = assess(candidate)
    assert result["status"] == "blocked", result
    assert any(b["code"] == "prescription_missing" and b["field"].endswith("legs") for b in result["blockers"]), result


@pytest.fixture
def edit_scope_candidate(candidate):
    """Future instructions plus preserved legacy identity detail outside edit scope."""
    from models.planning_build_confirmation import fingerprint
    from models.planning_build_readiness import forecast_build_input

    plan, response, context = candidate[2:]
    context["athlete_day"] = "2026-11-30"
    # This plan has one generated brick, all in the future. Preserve an
    # explicit historical brick identity fixture too. Its old dose/projection
    # is intentionally outside this build's prescription-validation scope.
    historical_day = next(day for day in plan["session_templates"] if day.get("sessions"))
    historical = deepcopy(composite(plan))
    historical["session_id"] = "preserved-brick"
    for index, child in enumerate(historical["legs"], 1):
        child["leg_id"] = f"preserved-brick:{index}"
    historical_day["sessions"].append(historical)
    context["parameters"]["action"] = "edit_current"
    context["lifecycle"]["action"] = "edit_current"
    response["lifecycle"] = deepcopy(context["lifecycle"])
    metrics = plan["forecast_input"]["initial_metrics"]
    # Use the actual forecast adapter, so an unrelated stale forecast cannot
    # manufacture a blocked result when isolating the identity boundary.
    rows = [(ps.datetime.fromisoformat(row["date"]), row["total_tss"], row["parts"])
            for row in plan["daily_plan"]]
    start, future = ps._cycle_forecast_input(rows, context["athlete_day"], context["lifecycle"]["end_date"])
    response["forecast"] = ps._forecast(ps.BanisterModel(), metrics, future, start,
                                       race_forecast_loads=plan.get("race_forecast_loads"))
    plan["forecast_input"] = forecast_build_input(plan, context, metrics)
    response["forecast"]["input_fingerprint"] = fingerprint(plan["forecast_input"])
    assert assess(candidate)["status"] == "ready", assess(candidate)
    return candidate


def scoped_identity_rows(candidate, *, past, leg):
    boundary = candidate[4]["athlete_day"]
    rows = []
    for day in candidate[2]["session_templates"]:
        if (day["date"] < boundary) != past:
            continue
        for session in day.get("sessions", []):
            if leg:
                rows.extend((day, session, child) for child in session.get("legs", []))
            else:
                rows.append((day, session, session))
    return rows


@pytest.mark.parametrize("past_leg", [False, True])
@pytest.mark.parametrize("future_leg", [False, True])
def test_future_identity_cannot_reuse_preserved_parent_or_leg(edit_scope_candidate, past_leg, future_leg):
    candidate = edit_scope_candidate
    old_day, _, old = scoped_identity_rows(candidate, past=True, leg=past_leg)[0]
    day, parent, assigned = scoped_identity_rows(candidate, past=False, leg=future_leg)[0]
    old_identity = old["leg_id" if past_leg else "session_id"]
    key = "leg_id" if future_leg else "session_id"
    assigned[key] = old_identity
    if day["sessions"][0] is parent:
        if future_leg:
            day["legs"] = deepcopy(parent["legs"])
        else:
            day["session_id"] = old_identity
    if not past_leg and not future_leg:
        from models.plan_actual_reconciliation import find_planned_session
        selected_day, _ = find_planned_session(candidate[2]["session_templates"], old_identity)
        assert selected_day["date"] == old_day["date"]
    before = deepcopy(candidate[2:])
    result = assess(candidate)
    assert result["status"] == "blocked", result
    reasons = [b for b in result["blockers"] if b["observed"] == old_identity]
    assert any(b["code"] == "prescription_missing" and b["date"] == day["date"]
               and b["leg_index"] == (assigned["leg_index"] if future_leg else None)
               and b["field"].endswith(key) for b in reasons), result
    assert not any(b["date"] == old_day["date"] for b in result["blockers"])
    assert candidate[2:] == before


def test_preserved_legacy_duplicates_and_invalid_instructions_are_not_reassessed(edit_scope_candidate):
    candidate = edit_scope_candidate
    history = scoped_identity_rows(candidate, past=True, leg=False)
    history[1][2]["session_id"] = history[0][2]["session_id"]
    for _, _, row in history:
        row["materialization_status"] = "legacy_role_fallback"
        row["materialized_steps"] = []
    before = deepcopy(candidate[2:])
    result = assess(candidate)
    assert result["status"] == "ready", result
    assert candidate[2:] == before

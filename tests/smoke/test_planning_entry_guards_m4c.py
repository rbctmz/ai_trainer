"""M4c fail-closed exposure partition, anchored edits and frozen publication."""

from copy import deepcopy
from datetime import date, timedelta, timezone
import json

import pytest

from api import planning_service as ps
from data import planning_build_preview_store as store
from models.planning_build_confirmation import (
    BuildParameters,
    PlanningBuildPreviewError,
    canonical_json,
)
from models.planning_entry_publication import (
    assess_entry_assignments,
    entry_base,
    entry_cap,
    entry_validation_context,
    execution_partition,
    historical_entry_load,
    validate_retained_entry,
    window_excess,
)
from services.planning_cycles import current_cycle_context
from tests.smoke.test_planning_entry_integration_m4c import (
    CAPS,
    prepared,
)
from tests.smoke.test_planning_entry_capture_m4b import all_tables
from tests.smoke._planning_build_confirmation import pin_clock
from tests.smoke._planning_entry_dose import exposure_db, entry_request


@pytest.fixture
def entry_scenario(tmp_path, monkeypatch):
    pin_clock(monkeypatch)
    db = exposure_db(tmp_path, ["running"] * 4)
    return db, entry_request(db, limits=deepcopy(CAPS))


def candidate(entry_scenario):
    db, raw = entry_scenario
    result = prepared(db, raw)
    plan = json.loads(result.checkpoint_json)["goal_plan_snapshot"]
    context = entry_validation_context(plan, result.snapshot.context())
    return db, result, plan, context


def row_for(db, result):
    return store.store_pending(
        db,
        result,
        origin="planning_ui",
        now=ps.datetime.now(timezone.utc),
        recheck=lambda conn: result.snapshot.dependency_digest,
    )


def rewrite(db, row, **fields):
    updated = {**row, **fields}
    updated["payload_digest"] = store._payload_digest(updated)
    if row["state"] == "applied":
        updated["applied_response_json"] = canonical_json(
            store._applied_response(updated, row["applied_checkpoint_id"])
        )
        updated["receipt_digest"] = store._receipt_digest(updated)
    changed = [k for k in updated if updated[k] != row[k]]
    with db._connect() as conn:
        conn.execute(
            f"UPDATE planning_build_previews SET {','.join(k + '=?' for k in changed)} WHERE preview_id=?",
            (*[updated[k] for k in changed], row["preview_id"]),
        )
    return updated


@pytest.mark.parametrize("side", ["before", "after", "frequency"])
def test_rolling_windows_cross_both_entry_boundaries(entry_scenario, side):
    _, _, plan, _ = candidate(entry_scenario)
    entry = plan["entry_load"]
    start = date.fromisoformat(entry["scope"]["start_date"])
    days = (
        [start - timedelta(days=1), start]
        if side == "before"
        else [start + timedelta(days=13), start + timedelta(days=14)]
    )
    minutes = 1 if side == "frequency" else 35
    excess = window_excess(
        [{"date": d.isoformat(), "sport": "bike", "minutes": minutes} for d in days],
        entry,
    )
    assert excess and all(r["sport"] == "bike" for r in excess)
    assert any(r["expected"]["minutes"] == 60 for r in excess)


def test_day_fifteen_continues_the_initial_envelope_without_goal_floor(entry_scenario):
    _, _, plan, _ = candidate(entry_scenario)
    entry = plan["entry_load"]
    cap = entry["limits"]["run"]
    assert entry_cap(cap, "2026-11-08", entry["scope"])["weekly_minutes"] == 40
    assert entry_cap(cap, "2026-11-09", entry["scope"])[
        "weekly_minutes"
    ] == pytest.approx(44)
    assert entry_cap(cap, "2026-12-14", entry["scope"])["weekly_sessions"] == 1


@pytest.mark.parametrize("kind", ["trusted", "heuristic", "foreign_cycle", "duplicate"])
def test_completed_identity_retires_only_trusted_owned_assignment_once(
    entry_scenario, kind
):
    _, _, _, context = candidate(entry_scenario)
    context["athlete_day"] = "2026-10-26"
    frozen = context["entry_inputs"]
    frozen.update(
        rows=[
            {
                "activity_id": "actual",
                "date": "2026-10-26",
                "sport": "running",
                "duration_minutes": 20,
                "tss": 0,
            }
        ],
        owned_sessions={"owned": {"date": "2026-10-26", "sport": "run"}},
        owned_checkpoint_ids=[10],
    )
    match = {
        "session_id": "owned",
        "session_date": "2026-10-26",
        "base_checkpoint_id": 10,
        "match_status": "matched",
        "match_method": "user_confirmed",
        "actual_activity_ids": ["actual"],
    }
    if kind == "heuristic":
        match["match_method"] = "date_sport"
    if kind == "foreign_cycle":
        match["base_checkpoint_id"] = 99
    frozen["matches"] = [match]
    if kind == "duplicate":
        frozen["owned_sessions"]["other"] = frozen["owned_sessions"]["owned"]
        frozen["matches"].append({**match, "session_id": "other"})
    actual = execution_partition(context)
    assert len(actual["actuals"]) == 1
    assert actual["retired_session_ids"] == (
        ["owned"] if kind in {"trusted", "duplicate"} else []
    )
    assert bool(actual["blockers"]) == (kind in {"heuristic", "duplicate"})


def test_same_day_unmatched_actual_is_never_silently_spent_again(entry_scenario):
    _, result, plan, context = candidate(entry_scenario)
    day = next(d for d in plan["session_templates"] if d.get("sessions"))
    session = day["sessions"][0]
    context["athlete_day"] = day["date"][:10]
    context["entry_inputs"]["rows"] = [
        {
            "activity_id": "today",
            "date": context["athlete_day"],
            "sport": session["sport"],
            "duration_minutes": 1,
            "tss": 0,
        }
    ]
    assessment = assess_entry_assignments(
        plan,
        entry_base(
            context, {**result.snapshot.parameters.as_dict(), "history_coverage": None}
        ),
        execution_partition(context),
        context=context,
    )
    assert not assessment["can_publish"]
    assert any(
        b["code"] == "execution_partition_ambiguous" for b in assessment["blockers"]
    )


def test_composite_legs_respect_their_own_discipline_and_session_caps(entry_scenario):
    _, result, plan, context = candidate(entry_scenario)
    day = next(d for d in plan["session_templates"] if d.get("sessions"))
    day["sessions"] = [
        {
            "kind": "composite",
            "session_id": "brick",
            "duration_minutes": 41,
            "legs": [
                {"sport": "bike", "duration_minutes": 1},
                {"sport": "run", "duration_minutes": 41},
            ],
        }
    ]
    assessment = assess_entry_assignments(
        plan,
        entry_base(
            context, {**result.snapshot.parameters.as_dict(), "history_coverage": None}
        ),
        execution_partition(context),
        context=context,
    )
    assert any(
        b["code"] == "entry_session_exceeded" and b["sport"] == "run"
        for b in assessment["blockers"]
    )


@pytest.mark.parametrize("bad", ["assessment", "evidence", "duration"])
def test_internal_corruption_is_500_before_any_active_write(entry_scenario, bad):
    db, result, plan, _ = candidate(entry_scenario)
    row = row_for(db, result)
    response = json.loads(row["response_json"])
    if bad == "assessment":
        plan["entry_load"]["limits"]["run"]["weekly_minutes"] += 1
        response["entry_load"] = plan["entry_load"]
    elif bad == "evidence":
        plan["entry_evidence"]["rows"][0]["duration_minutes"] += 1
    else:
        next(t for t in plan["session_templates"] if t.get("sessions"))["sessions"][0][
            "duration_minutes"
        ] = 999
    checkpoint = json.loads(row["checkpoint_json"])
    checkpoint["goal_plan_snapshot"] = plan
    rewrite(
        db,
        row,
        checkpoint_json=canonical_json(checkpoint),
        response_json=canonical_json(response),
    )
    before = all_tables(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        ps.confirm_plan_build(db, preview_id=row["preview_id"], origin="planning_ui")
    assert (error.value.code, error.value.status) == ("preview_corrupt", 500)
    assert all_tables(db) == before


def test_honestly_blocked_retained_result_cannot_publish(entry_scenario):
    db, raw = entry_scenario
    raw["initial_dose_limits"]["swim"].update(weekly_minutes=1, max_session_minutes=1)
    result = prepared(db, raw)
    assert json.loads(result.response_json)["entry_load"]["status"] == "blocked"
    row = row_for(db, result)
    before = all_tables(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        ps.confirm_plan_build(db, preview_id=row["preview_id"], origin="planning_ui")
    assert (error.value.code, error.value.status) == ("entry_dose_infeasible", 409)
    assert all_tables(db) == before


@pytest.mark.parametrize("applied", [False, True])
def test_pre_m4_pending_refreshes_but_applied_receipt_replays_before_new_gate(
    entry_scenario, applied, monkeypatch
):
    db, result, plan, _ = candidate(entry_scenario)
    shown = ps.prepare_plan_build(
        db,
        parameters=BuildParameters.from_mapping(entry_scenario[1]),
        origin="planning_ui",
    )
    token = shown["confirmation"]["preview_id"]
    if applied:
        ps.confirm_plan_build(db, preview_id=token, origin="planning_ui")
    row = store.get_preview(db, token, origin="planning_ui")
    checkpoint = json.loads(row["checkpoint_json"])
    response = json.loads(row["response_json"])
    checkpoint["goal_plan_snapshot"].pop("entry_load")
    checkpoint["goal_plan_snapshot"].pop("entry_evidence")
    response.pop("entry_load")
    rewrite(
        db,
        row,
        checkpoint_json=canonical_json(checkpoint),
        response_json=canonical_json(response),
    )
    before = all_tables(db)
    if applied:
        monkeypatch.setattr(
            ps,
            "_capture_plan_build_inputs",
            lambda *a, **k: pytest.fail("replay must not capture"),
        )
        saved = ps.confirm_plan_build(db, preview_id=token, origin="planning_ui")
        assert saved["confirmation"]["replayed"] and "entry_load" not in saved
    else:
        with pytest.raises(PlanningBuildPreviewError) as error:
            ps.confirm_plan_build(db, preview_id=token, origin="planning_ui")
        assert (error.value.code, error.value.status) == ("preview_required", 409)
    assert all_tables(db) == before


def test_frozen_guard_uses_no_live_recapture_planner_or_banister(
    entry_scenario, monkeypatch
):
    db, result, _, _ = candidate(entry_scenario)
    row = row_for(db, result)

    def forbidden(*a, **k):
        pytest.fail("frozen guard accessed runtime")

    monkeypatch.setattr(db, "_connect", forbidden)
    monkeypatch.setattr(ps, "_capture_plan_build_inputs", forbidden)
    monkeypatch.setattr(ps, "_calculate_plan_build", forbidden)
    monkeypatch.setattr(ps, "athlete_local_date", forbidden)
    validate_retained_entry(row)


def test_edit_retains_original_entry_scope_and_limit_sources(entry_scenario):
    db, raw = entry_scenario
    raw.update(start_date="2026-10-28", start_week="2026-10-26")
    shown = ps.prepare_plan_build(
        db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui"
    )
    saved = ps.confirm_plan_build(
        db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui"
    )
    current = current_cycle_context(db)
    raw.update(
        action="edit_current",
        base_cycle_id=current["cycle_id"],
        base_cycle_revision=current["cycle_revision"],
        base_selection_revision=current["selection_revision"],
        base_checkpoint_id=current["checkpoint_id"],
        replace_current_cycle=False,
    )
    raw.pop("initial_dose_limits")
    raw.pop("history_coverage")
    edit = prepared(db, raw)
    final = json.loads(edit.response_json)["entry_load"]
    assert (
        final["scope"]
        == saved["entry_load"]["scope"]
        == {"start_date": "2026-10-28", "end_date": "2026-11-10"}
    )
    assert final["limits"] == saved["entry_load"]["limits"]
    assert final["profile"]["completeness"]["status"] == "unknown"
    assert any(w["code"] == "entry_limits_retained" for w in final["warnings"])


def test_historical_unassessed_projection_is_read_only_and_null(entry_scenario):
    _, _, plan, _ = candidate(entry_scenario)
    old = deepcopy(plan)
    old.pop("entry_load")
    before = deepcopy(old)
    assert historical_entry_load(old) == {
        "policy_version": None,
        "scope": None,
        "profile": None,
        "status": "unassessed",
        "can_publish": False,
        "limits": {},
        "blockers": [],
        "warnings": [],
    }
    assert old == before


def test_completed_entry_session_also_respects_maximum_session_cap(entry_scenario):
    _, result, _, context = candidate(entry_scenario)
    base = entry_base(context, result.snapshot.parameters.as_dict())
    base["limits"]["run"].update(weekly_minutes=100, max_session_minutes=40)
    context["athlete_day"] = "2026-10-26"
    context["entry_inputs"]["target_sports"] = ["run"]
    execution = {
        "actuals": [
            {
                "activity_id": "long-run",
                "date": "2026-10-26",
                "sport": "run",
                "minutes": 41,
            }
        ],
        "retired_session_ids": [],
        "blockers": [],
    }
    final = assess_entry_assignments(
        {"session_templates": []}, base, execution, context=context
    )
    assert any(
        b["code"] == "entry_session_exceeded" and b["sport"] == "run"
        for b in final["blockers"]
    )


def test_race_specific_phase_never_retimes_into_different_role(
    entry_scenario, monkeypatch
):
    from models import planning_entry_generation as generation

    _, result, plan, context = candidate(entry_scenario)
    base = entry_base(context, result.snapshot.parameters.as_dict())
    plan["daily_plan"] = [
        (d["date"], d["total_tss"], d["parts"]) for d in plan["daily_plan"]
    ]
    template = next(t for t in plan["session_templates"] if t.get("sessions"))
    template.update(phase="Peak", protected_by_event=None)
    session = template["sessions"][0]
    session.update(session_role="threshold", duration_minutes=100, total_tss=100)

    def incompatible(**kwargs):
        return {
            "materialization_status": "materialized",
            "duration_minutes": 5,
            "parameter_snapshot": {"target_tss": 1},
            "session_role": "easy",
            "template_key": "fallback-easy",
            "sport": session["sport"],
        }

    monkeypatch.setattr(generation, "materialize_session_template", incompatible)
    output = generation.constrain_entry_assignments(
        plan,
        base,
        {"actuals": [], "retired_session_ids": [], "blockers": []},
        context=context,
        zones={},
    )
    changed = next(
        t for t in output["session_templates"] if t["date"] == template["date"]
    )
    assert changed["sessions"][0]["session_role"] == "threshold"
    assert changed["sessions"][0]["duration_minutes"] == 100


@pytest.mark.parametrize("change", ["duration", "lineage", "policy"])
def test_entry_dependency_change_invalidates_pending_without_active_write(
    entry_scenario, monkeypatch, change
):
    from tests.smoke._planning_build_confirmation import protected_state

    db, raw = entry_scenario
    shown = ps.prepare_plan_build(
        db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui"
    )
    if change == "policy":
        monkeypatch.setattr(ps, "ENTRY_LOAD_POLICY_VERSION", "entry-load-next")
    else:
        with db._connect() as conn:
            if change == "duration":
                conn.execute(
                    "UPDATE activities SET duration_minutes=duration_minutes+1 WHERE activity_id='recent-0'"
                )
            else:
                conn.execute(
                    "INSERT INTO activity_provider_links(canonical_activity_id,provider,provider_activity_id,external_provider,external_id) VALUES('recent-0','intervals','test-link','garmin','recent-1')"
                )
    before = protected_state(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        ps.confirm_plan_build(
            db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui"
        )
    assert error.value.code == "preview_stale"
    assert protected_state(db) == before
    assert (
        store.get_preview(
            db, shown["confirmation"]["preview_id"], origin="planning_ui"
        )["state"]
        == "invalidated"
    )


def test_undated_quality_gap_is_captured_and_refuses_despite_explicit_limits(
    entry_scenario,
):
    db, raw = entry_scenario
    with db._connect() as conn:
        conn.execute(
            "INSERT INTO activities(activity_id,date,sport,duration_minutes,tss) VALUES('undated','invalid','cycling',20,10)"
        )
    before = all_tables(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        ps.prepare_plan_build(
            db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui"
        )
    assert error.value.code == "entry_dose_infeasible"
    assert any(
        b["observed"] == "activity_date_invalid"
        for b in error.value.context["entry_load"]["blockers"]
    )
    assert all_tables(db) == before


def test_original_entry_actuals_are_captured_even_outside_ordinary_history_window(
    entry_scenario,
):
    import pandas as pd
    from services.planning_entry_capture import capture_entry_inputs

    db, raw = entry_scenario
    result = prepared(db, raw)
    lifecycle = result.snapshot.context()["lifecycle"]
    with db._connect() as conn:
        conn.execute(
            "INSERT INTO activities(activity_id,date,sport,duration_minutes,tss) VALUES('old-entry','2026-11-14T12:00:00Z','cycling',20,10)"
        )
    before = all_tables(db)
    with db._connect() as conn:
        frozen = capture_entry_inputs(
            conn, pd.DataFrame(), None, lifecycle, result.snapshot.parameters.as_dict()
        )
    assert any(r["activity_id"] == "old-entry" for r in frozen["rows"])
    assert all_tables(db) == before


@pytest.mark.parametrize("method", ["user_confirmed", "date_sport"])
def test_edit_counts_actual_once_and_does_not_reassign_confirmed_workout(
    entry_scenario, monkeypatch, method
):
    db, raw = entry_scenario
    shown = ps.prepare_plan_build(
        db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui"
    )
    saved = ps.confirm_plan_build(
        db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui"
    )
    plan = db.get_current_planning_checkpoint()["goal_plan_snapshot"]
    template = next(t for t in plan["session_templates"] if t.get("sessions"))
    session = template["sessions"][0]
    day = template["date"][:10]
    monkeypatch.setattr(ps, "athlete_local_date", lambda: date.fromisoformat(day))
    with db._connect() as conn:
        conn.execute(
            "INSERT INTO activities(activity_id,date,sport,duration_minutes,tss,tss_method) VALUES('completed-entry',?,?,?,?,?)",
            (
                day,
                session["sport"],
                session["duration_minutes"],
                session["total_tss"],
                "synthetic_fixed",
            ),
        )
    db.save_plan_actual_match(
        {
            "fingerprint": "entry-completed",
            "target_key": f"session:{session['session_id']}",
            "session_id": session["session_id"],
            "base_checkpoint_id": int(saved["plan_id"]),
            "session_date": day,
            "match_status": "matched",
            "match_method": method,
            "confidence": 1.0,
            "planned_snapshot": session,
            "actual_activity_ids": ["completed-entry"],
            "actual_snapshot": {"tss": session["total_tss"]},
            "evidence": {"source": "synthetic"},
            "rule_version": "synthetic-v1",
        }
    )
    c = current_cycle_context(db)
    raw.update(
        action="edit_current",
        base_cycle_id=c["cycle_id"],
        base_cycle_revision=c["cycle_revision"],
        base_selection_revision=c["selection_revision"],
        base_checkpoint_id=c["checkpoint_id"],
        replace_current_cycle=False,
    )
    raw.pop("initial_dose_limits")
    raw.pop("history_coverage")
    before = all_tables(db)
    result = prepared(db, raw)
    final = json.loads(result.checkpoint_json)["goal_plan_snapshot"]
    if method == "user_confirmed":
        assert final["entry_load"]["status"] == "supported", final["entry_load"][
            "blockers"
        ]
        context = entry_validation_context(final, result.snapshot.context())
        assert (
            session["session_id"] in execution_partition(context)["retired_session_ids"]
        )
        assert not any(
            s.get("session_id") == session["session_id"]
            or s.get("replaces_session_id") == session["session_id"]
            for t in final["session_templates"]
            for s in t.get("sessions", [])
        )
    else:
        assert final["entry_load"]["status"] == "blocked"
        assert any(
            b["code"] == "execution_partition_ambiguous"
            for b in final["entry_load"]["blockers"]
        )
    assert all_tables(db) == before


def test_other_checkpoint_writers_drop_supported_entry_evidence(entry_scenario):
    from models.planning_checkpoints import (
        build_planning_checkpoint,
        restore_goal_plan_from_checkpoint,
    )

    _, result, _, _ = candidate(entry_scenario)
    plan = restore_goal_plan_from_checkpoint(json.loads(result.checkpoint_json))
    rewritten = build_planning_checkpoint(plan)["goal_plan_snapshot"]
    assert "entry_load" not in rewritten and "entry_evidence" not in rewritten
    assert historical_entry_load(rewritten)["status"] == "unassessed"


def test_marker_coach_preserves_nested_explicit_dose_and_rejects_missing_baseline(
    entry_scenario,
):
    from models.ai_coach_runtime import _parse_tool_params
    from models.ai_tools import AITools

    db, raw = entry_scenario
    values = _parse_tool_params(
        f'initial_dose_limits={json.dumps(CAPS)}, history_coverage={{"status":"unknown"}}, action=start_new'
    )
    assert values["initial_dose_limits"] == CAPS
    assert values["history_coverage"] == {"status": "unknown"}
    values = _parse_tool_params("initial_dose_limits={invalid}, action=start_new")
    assert values["initial_dose_limits"] == "{invalid}"
    raw.pop("initial_dose_limits")
    raw.pop("history_coverage")
    raw.pop("events")
    for key in (
        "planning_mode",
        "horizon_weeks",
        "intent",
        "focus",
        "manual_phases",
        "demand",
        "start_week",
    ):
        raw.pop(key, None)
    before = all_tables(db)
    refused = AITools(db).propose_plan_build(**{**raw, "event_date": "2027-02-13"})
    assert refused["success"] is False and refused["code"] == "entry_dose_required"
    assert "entry_load" in refused and "preview_id" not in refused
    assert all_tables(db) == before

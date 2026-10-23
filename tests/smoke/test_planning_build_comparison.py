"""Frozen comparison behavior; all inputs are synthetic saved JSON."""
from copy import deepcopy
from datetime import date, timedelta

import pytest

from models.planning_build_comparison import build_plan_comparison


def session(*, minutes=30, tss=20, target=0.6, identity="one"):
    return {"session_id": identity, "kind": "single", "sport": "run", "session_role": "easy",
            "session_focus": "base", "template_name": "Easy run", "duration_minutes": minutes,
            "total_tss": tss, "materialization_status": "supported", "structure_status": "ready",
            "materialized_steps": [{"name": "run", "intensity": "easy", "segment_kind": "work",
                                    "duration_seconds": minutes * 60, "target": {"rpe": target}}]}


def checkpoint(start="2026-10-26", days=3):
    first = date.fromisoformat(start)
    daily, templates = [], []
    for index in range(days):
        dt = (first + timedelta(days=index)).isoformat()
        daily.append({"date": dt, "total_tss": 20.0, "parts": {"run": 20.0}})
        templates.append({"date": dt, "phase": "Base", "sessions": [session(identity=f"s{index}")]})
    weeks = sorted({(first + timedelta(days=i) - timedelta(days=(first + timedelta(days=i)).weekday())).isoformat() for i in range(days)})
    return {"id": 7, "goal_plan_snapshot": {"goal_type": "Триатлон", "distance": "Олимпийка",
        "planning_mode": "training_goal", "planning_intent": "develop", "planning_focus": "balanced_triathlon",
        "demand_level": "moderate", "events": [], "constraint_summary": {"available_hours": 10.0, "available_day_indices": [0, 1, 2]},
        "daily_plan": daily, "session_templates": templates, "weekly_summary": [{"week_start": w} for w in weeks]}}


def compare(before=None, after=None, *, action="edit_current"):
    before = checkpoint() if before is None else before
    after = deepcopy(before) if after is None else after
    old = before["goal_plan_snapshot"]["daily_plan"]
    new = after["goal_plan_snapshot"]["daily_plan"]
    context = {"lifecycle": {"action": action, "base_checkpoint_id": before["id"], "source_cycle_id": "old-cycle", "base_cycle_revision": 2,
        "start_date": new[0]["date"][:10], "end_date": new[-1]["date"][:10], "closes_cycle_id": "old-cycle" if action == "start_new" else None},
        "cycle_ownership": {"cycle": {"start_date": old[0]["date"][:10], "end_date": old[-1]["date"][:10]}}}
    params = {"goal_type": "triathlon", "distance": "olympic", "planning_mode": "training_goal", "intent": "develop",
              "focus": "balanced_triathlon", "demand": "moderate", "available_hours": 10.0, "available_days": ["mon", "tue", "wed"]}
    return build_plan_comparison(before, after, params, context)


def test_same_content_is_unchanged_and_inputs_not_mutated():
    before = checkpoint()
    after = deepcopy(before)
    after["goal_plan_snapshot"]["session_templates"][0]["sessions"][0].update(session_id="new", session_identity_namespace="new-cycle", catalog_version="new-version")
    original = deepcopy((before, after))
    result = compare(before, after)
    assert (before, after) == original
    assert result["status"] == "complete"
    assert result["before"]["total_tss"] == result["after"]["total_tss"] == 60
    assert result["counts"] == {"added": 0, "removed": 0, "changed": 0, "unchanged": 3, "unknown": 0}
    assert result["base_checkpoint_id"] == 7


def test_shortened_period_does_not_compare_totals_as_weekly_delta():
    before, after = checkpoint(days=8), checkpoint(days=4)
    result = compare(before, after)
    assert result["before"]["scope"] == {"start_date": "2026-10-26", "end_date": "2026-11-02"}
    assert result["after"]["total_tss"] == 80
    assert result["before"]["total_tss"] == 160
    assert result["counts"]["removed"] == 4
    assert "delta" not in result
    assert result["days"][-1]["after"]["state"] == "outside"


def test_changed_prescription_same_tss_and_minutes_is_changed():
    before, after = checkpoint(), checkpoint()
    after["goal_plan_snapshot"]["session_templates"][1]["sessions"][0]["materialized_steps"][0]["target"] = {"rpe": 0.9}
    result = compare(before, after)
    assert result["counts"]["changed"] == 1
    assert result["days"][1]["change"] == "changed"


def test_reordering_multiple_sessions_is_not_a_change_but_duplicates_count():
    before, after = checkpoint(), checkpoint()
    for cp in (before, after):
        cp["goal_plan_snapshot"]["session_templates"][0]["sessions"].append(session(minutes=40))
        cp["goal_plan_snapshot"]["daily_plan"][0]["total_tss"] = 40
    after["goal_plan_snapshot"]["session_templates"][0]["sessions"].reverse()
    assert compare(before, after)["days"][0]["change"] == "unchanged"
    after["goal_plan_snapshot"]["session_templates"][0]["sessions"].append(session())
    after["goal_plan_snapshot"]["daily_plan"][0]["total_tss"] = 60
    assert compare(before, after)["days"][0]["change"] == "changed"


def test_missing_interior_day_and_missing_sessions_are_unknown_not_rest():
    before, after = checkpoint(), checkpoint()
    before["goal_plan_snapshot"]["daily_plan"].pop(1)
    result = compare(before, after)
    assert result["status"] == "partial" and result["counts"] is None
    assert result["before"]["total_tss"] is None
    assert result["days"][1]["before"]["state"] == "unknown"
    before = checkpoint()
    before["goal_plan_snapshot"]["session_templates"][0].pop("sessions")
    assert compare(before, after)["days"][0]["change"] == "unknown"


def test_rest_to_outside_is_not_removed_workout():
    before, after = checkpoint(), checkpoint(days=2)
    before["goal_plan_snapshot"]["daily_plan"][-1]["total_tss"] = 0
    before["goal_plan_snapshot"]["session_templates"][-1]["sessions"] = []
    result = compare(before, after)
    assert result["days"][-1]["before"]["state"] == "rest"
    assert result["days"][-1]["change"] == "unchanged"


def test_sparse_huge_span_never_expands_calendar_or_counts_as_deleted():
    before, after = checkpoint(), checkpoint()
    before["goal_plan_snapshot"]["daily_plan"][-1]["date"] = "9999-12-31"
    result = compare(before, after)
    assert result["before"]["schedule_status"] == "unavailable"
    assert "schedule_too_large" in result["before"]["reasons"]
    assert len(result["days"]) <= 3 and result["counts"] is None


def test_old_missing_availability_is_not_read_from_new_parameters():
    before = checkpoint()
    before["goal_plan_snapshot"]["constraint_summary"] = {}
    result = compare(before, checkpoint())
    assert result["before"]["parameters"]["available_hours"] is None
    assert result["after"]["parameters"]["available_hours"] == 10
    assert result["status"] == "partial"


def test_no_baseline_is_not_a_zero_old_plan():
    after = checkpoint()
    params = {"goal_type": "triathlon", "distance": "olympic"}
    context = {"lifecycle": {"action": "start_new", "base_checkpoint_id": 0, "source_cycle_id": None,
               "base_cycle_revision": None, "start_date": "2026-10-26", "end_date": "2026-10-28"}}
    result = build_plan_comparison(None, after, params, context)
    assert result["status"] == "no_baseline" and result["before"] is None
    assert result["counts"] is None
    assert all(day["change"] == "unknown" for day in result["days"])


def test_disjoint_periods_are_joined_by_date_not_array_index():
    result = compare(checkpoint(), checkpoint("2026-12-07"), action="start_new")
    assert len(result["days"]) == 6
    assert result["counts"]["added"] == result["counts"]["removed"] == 3
    assert result["base_cycle_id"] == "old-cycle"


def test_malformed_steps_and_duplicate_dates_are_unknown():
    before, after = checkpoint(), checkpoint()
    before["goal_plan_snapshot"]["session_templates"][0]["sessions"][0]["materialized_steps"] = [None]
    assert compare(before, after)["days"][0]["change"] == "unknown"
    before = checkpoint()
    before["goal_plan_snapshot"]["daily_plan"][1]["date"] = "2026-10-26"
    result = compare(before, after)
    assert result["status"] == "partial" and result["counts"] is None
    assert all(day["change"] == "unknown" for day in result["days"])


def test_composite_leg_order_is_content_but_leg_ids_are_not():
    before, after = checkpoint(), checkpoint()
    for cp in (before, after):
        cp["goal_plan_snapshot"]["session_templates"][0]["sessions"] = [{
            "kind": "composite", "duration_minutes": 70, "total_tss": 40,
            "sport": "brick", "legs": [session(), session(minutes=40)]}]
        cp["goal_plan_snapshot"]["daily_plan"][0]["total_tss"] = 40
    after["goal_plan_snapshot"]["session_templates"][0]["sessions"][0]["legs"][0]["leg_id"] = "new"
    assert compare(before, after)["days"][0]["change"] == "unchanged"
    after["goal_plan_snapshot"]["session_templates"][0]["sessions"][0]["legs"].reverse()
    assert compare(before, after)["days"][0]["change"] == "changed"


def test_selected_baseline_identity_must_match():
    before, after = checkpoint(), checkpoint()
    with pytest.raises(ValueError, match="Исходная версия"):
        build_plan_comparison(before, after, {}, {"lifecycle": {"base_checkpoint_id": 99}})


def test_missing_old_week_summary_retains_only_proven_total():
    before = checkpoint()
    before["goal_plan_snapshot"].pop("weekly_summary")
    result = compare(before, checkpoint())
    assert result["before"]["total_tss"] == 60
    assert result["before"]["peak_tss"] is None and result["status"] == "partial"


def _actual_edit(tmp_path, monkeypatch):
    from api import planning_service as ps
    from models.planning_build_confirmation import BuildParameters
    from services.planning_cycles import current_cycle_context
    from tests.smoke._planning_build_confirmation import declared_entry_limits, pin_clock
    from tests.smoke._planning_entry_dose import entry_request, exposure_db

    pin_clock(monkeypatch)
    db = exposure_db(tmp_path, ["running"] * 4)
    raw = entry_request(db, limits=declared_entry_limits(8))
    first = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui")
    ps.confirm_plan_build(db, preview_id=first["confirmation"]["preview_id"], origin="planning_ui")
    current = current_cycle_context(db)
    raw.update(action="edit_current", base_cycle_id=current["cycle_id"], base_cycle_revision=current["cycle_revision"],
               base_selection_revision=current["selection_revision"], base_checkpoint_id=current["checkpoint_id"],
               replace_current_cycle=False, horizon_weeks=4)
    raw.pop("initial_dose_limits")
    raw.pop("history_coverage")
    edit = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui")
    return db, first, edit


def test_actual_public_edit_has_typed_frozen_scoped_comparison_and_historical_replay(tmp_path, monkeypatch):
    from api import planning_service as ps
    from api.planning_build_contract import BuildPreviewResponseV2

    db, first, edit = _actual_edit(tmp_path, monkeypatch)
    BuildPreviewResponseV2.model_validate(edit)
    comparison = edit["comparison"]
    assert comparison["status"] == "complete"
    assert comparison["before"]["scope"]["end_date"] == "2026-12-20"
    assert comparison["after"]["scope"]["end_date"] == "2026-11-22"
    assert comparison["before"]["total_tss"] == first["totals"]["total_tss"] == 999
    assert comparison["after"]["total_tss"] == edit["totals"]["total_tss"] == 433
    assert comparison["after"]["peak_tss"] == edit["totals"]["peak_tss"]
    assert comparison["base_checkpoint_id"] == edit["lifecycle"]["base_checkpoint_id"]
    assert comparison["before"]["parameters"]["available_hours"] == 10
    saved = ps.confirm_plan_build(db, preview_id=edit["confirmation"]["preview_id"], origin="planning_ui")
    assert saved["comparison"] == comparison
    replay = ps.confirm_plan_build(db, preview_id=edit["confirmation"]["preview_id"], origin="planning_ui")
    assert replay["comparison"] == comparison and replay["confirmation"]["replayed"]
    historical = ps.confirm_plan_build(db, preview_id=first["confirmation"]["preview_id"], origin="planning_ui")
    assert historical["comparison"] == first["comparison"]
    assert historical["confirmation"]["is_current"] is False


def test_legacy_optional_response_stays_readable_without_comparison(tmp_path, monkeypatch):
    from api.planning_build_contract import BuildPreviewResponseV2

    _, _, edit = _actual_edit(tmp_path, monkeypatch)
    edit.pop("comparison")
    assert BuildPreviewResponseV2.model_validate(edit).comparison is None


@pytest.mark.parametrize("days,expected", [(366, "complete"), (367, "unavailable")])
def test_calendar_row_bound_is_explicit(days, expected):
    before = checkpoint(days=days)
    result = compare(before, checkpoint())
    assert result["before"]["schedule_status"] == expected
    assert len(result["days"]) <= 732


def test_complete_zero_rest_values_are_not_unknown():
    before, after = checkpoint(), checkpoint()
    for cp in (before, after):
        cp["goal_plan_snapshot"]["constraint_summary"]["available_hours"] = 0
        cp["goal_plan_snapshot"]["daily_plan"][0]["total_tss"] = 0
        cp["goal_plan_snapshot"]["session_templates"][0]["sessions"] = []
    result = compare(before, after)
    assert result["before"]["parameters"]["available_hours"] == 0
    assert result["days"][0]["before"]["state"] == "rest"
    assert result["days"][0]["before"]["tss"] == 0


def test_selected_but_unreadable_replacement_baseline_is_partial_not_new_gate():
    result = build_plan_comparison(None, checkpoint(), {}, {"lifecycle": {
        "action": "start_new", "source_cycle_id": "old-cycle", "base_checkpoint_id": 7,
        "closes_cycle_id": "old-cycle", "start_date": "2026-10-26", "end_date": "2026-10-28"}})
    assert result["status"] == "partial" and result["before"] is not None
    assert result["before"]["scope"] is None and result["counts"] is None
    assert all(day["change"] == "unknown" for day in result["days"])


def test_invalid_old_events_and_nonfinite_loads_remain_unknown():
    before = checkpoint()
    before["goal_plan_snapshot"]["events"] = [{"label": "unscoped"}]
    before["goal_plan_snapshot"]["daily_plan"][0]["total_tss"] = 10 ** 400
    result = compare(before, checkpoint())
    assert result["before"]["parameters"]["events"] is None
    assert result["before"]["total_tss"] is None
    assert result["days"][0]["before"]["state"] == "unknown"


@pytest.mark.parametrize("steps", [[], [{}], [{"duration_seconds": 30}], [{"duration_seconds": 0, "target": {"rpe": 2}}]])
def test_incomplete_prescription_steps_do_not_become_a_known_change(steps):
    before = checkpoint()
    before["goal_plan_snapshot"]["session_templates"][0]["sessions"][0]["materialized_steps"] = steps
    result = compare(before, checkpoint())
    assert result["status"] == "partial" and result["counts"] is None
    assert result["days"][0]["before"]["state"] == "unknown"
    assert result["days"][0]["change"] == "unknown"


def test_reordered_templates_are_matched_by_own_date_not_index():
    before = checkpoint()
    before["goal_plan_snapshot"]["session_templates"][1]["sessions"][0] = session(minutes=40)
    after = deepcopy(before)
    after["goal_plan_snapshot"]["session_templates"].reverse()
    result = compare(before, after)
    assert result["status"] == "complete"
    assert all(row["change"] == "unchanged" for row in result["days"])
    assert result["days"][1]["before"]["sessions"][0]["minutes"] == 40

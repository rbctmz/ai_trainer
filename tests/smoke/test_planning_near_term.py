from __future__ import annotations

from datetime import date

import pytest

from models.planning_checkpoints import build_planning_checkpoint
from models.planning_near_term import (
    apply_near_term_day_edits,
    build_near_term_edit_draft_rows,
    build_near_term_edit_seed_from_goal_plans,
    build_near_term_edit_rows,
    build_safer_near_term_draft,
    summarize_near_term_draft_rows,
)
from models.training_planner import build_daily_session_templates, expand_weekly_to_daily_triathlon


pytestmark = pytest.mark.smoke


def _sample_goal_plan():
    weekly_tss_plan = [220, 240, 180]
    phases = ["Base", "Build", "Taper"]
    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        weekly_tss_plan,
        phases,
        "Олимпийка",
        date(2026, 6, 8),
        goal_type="Триатлон",
        load_state="balanced",
    )
    session_templates = build_daily_session_templates(
        daily_plan,
        weekly_summary,
        goal_type="Триатлон",
        distance="Олимпийка",
    )
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "weeks_to_race": len(weekly_tss_plan),
        "start_week": date(2026, 6, 8),
        "weekly_tss_plan": weekly_tss_plan,
        "base_weekly_tss_plan": [220, 240, 180],
        "phases": phases,
        "daily_plan": daily_plan,
        "session_templates": session_templates,
        "weekly_summary": weekly_summary,
        "constraint_summary": {
            "catch_up_strategy": "catch_up",
            "current_tsb": -4.0,
            "load_state": "balanced",
            "notes": ["Базовый план под текущую доступность."],
        },
    }


def test_build_near_term_edit_rows_limits_horizon_and_preserves_defaults():
    goal_plan = _sample_goal_plan()

    rows = build_near_term_edit_rows(goal_plan, horizon_days=12)

    assert len(rows) == 10
    assert rows[0]["date_label"].startswith("Пн")
    assert rows[0]["current_role"] in {"off", "recovery", "easy", "quality", "long"}
    assert rows[0]["current_sport"] in {"run", "bike", "swim", "off"}


def test_apply_near_term_day_edits_updates_daily_plan_templates_and_weekly_totals():
    goal_plan = _sample_goal_plan()
    original_week_two_total = goal_plan["weekly_tss_plan"][1]
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)

    updated_goal_plan = apply_near_term_day_edits(
        goal_plan,
        [
            {
                **edit_rows[0],
                "session_role": "off",
                "sport": "off",
                "total_tss": 0,
            },
            {
                **edit_rows[1],
                "session_role": "quality",
                "sport": "run",
                "total_tss": 95,
            },
        ],
        horizon_days=7,
    )

    first_day = updated_goal_plan["daily_plan"][0]
    second_day = updated_goal_plan["daily_plan"][1]

    assert first_day[1] == 0.0
    assert sum(first_day[2].values()) == 0.0
    assert second_day[1] == 95.0
    assert second_day[2]["run"] == 95.0
    assert second_day[2]["bike"] == 0.0
    assert updated_goal_plan["session_templates"][0]["session_role"] == "off"
    assert updated_goal_plan["session_templates"][1]["sport"] == "run"
    assert updated_goal_plan["session_templates"][1]["session_focus"] == "Качество • бег"
    assert updated_goal_plan["weekly_tss_plan"][0] != goal_plan["weekly_tss_plan"][0]
    assert updated_goal_plan["weekly_summary"][0]["weekly_tss"] == updated_goal_plan["weekly_tss_plan"][0]
    assert "ручная правка:" in updated_goal_plan["weekly_summary"][0]["adjustment_note"]
    assert updated_goal_plan["weekly_tss_plan"][1] == original_week_two_total
    assert updated_goal_plan["constraint_summary"]["near_term_edit"]["is_active"] is True
    assert updated_goal_plan["constraint_summary"]["near_term_edit"]["horizon_days"] == 7
    assert updated_goal_plan["constraint_summary"]["near_term_edit"]["post_edit_strategy"] == "keep"
    assert updated_goal_plan["constraint_summary"]["near_term_edit"]["risk_level"] in {"low", "medium", "high"}
    assert updated_goal_plan["near_term_edit_version"] == 1


def test_build_near_term_edit_draft_rows_exposes_preview_ready_changes():
    goal_plan = _sample_goal_plan()
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)

    draft_rows = build_near_term_edit_draft_rows(
        edit_rows,
        goal_type=goal_plan["goal_type"],
        distance=goal_plan["distance"],
        overrides_by_index={
            0: {
                "session_role": "off",
                "sport": "off",
                "total_tss": 0,
            },
            1: {
                "session_role": "quality",
                "sport": "run",
                "total_tss": 95,
            },
        },
    )

    assert draft_rows[0]["changed"] is True
    assert draft_rows[0]["target_summary"].startswith("Отдых")
    assert draft_rows[0]["target_duration_minutes"] == 0
    assert draft_rows[1]["target_focus"] == "Качество • бег"
    assert draft_rows[1]["target_export_name"].startswith("Триатлон Олимпийка")
    assert draft_rows[1]["delta_tss"] > 0


def test_single_session_cannot_be_converted_to_brick():
    goal_plan = _sample_goal_plan()
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)
    row = next(item for item in edit_rows if item["current_sport"] != "off")
    index = int(row["index"])
    original_day = goal_plan["daily_plan"][index]
    original_template = goal_plan["session_templates"][index]

    draft_rows = build_near_term_edit_draft_rows(
        [row],
        goal_type=goal_plan["goal_type"],
        distance=goal_plan["distance"],
        overrides_by_index={index: {"sport": "brick"}},
    )

    assert row["current_kind"] == "single"
    assert draft_rows[0]["sport"] == row["current_sport"]
    assert draft_rows[0]["changed"] is False

    updated = apply_near_term_day_edits(
        goal_plan,
        [
            {
                **row,
                "session_role": row["current_role"],
                "sport": "brick",
                "total_tss": row["current_total_tss"],
            }
        ],
        horizon_days=7,
    )

    assert updated["daily_plan"][index] == original_day
    updated_template = updated["session_templates"][index]
    assert updated_template["kind"] == "single"
    assert updated_template["sport"] == original_template["sport"]
    assert updated_template["materialized_steps"] == original_template["materialized_steps"]
    assert (
        updated_template["prescription_fingerprint"]
        == original_template["prescription_fingerprint"]
    )


def test_summarize_near_term_draft_rows_returns_compact_diff_summary():
    goal_plan = _sample_goal_plan()
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)
    draft_rows = build_near_term_edit_draft_rows(
        edit_rows,
        goal_type=goal_plan["goal_type"],
        distance=goal_plan["distance"],
        overrides_by_index={
            0: {
                "session_role": "off",
                "sport": "off",
                "total_tss": 0,
            },
            1: {
                "session_role": "quality",
                "sport": "run",
                "total_tss": 95,
            },
        },
    )

    summary = summarize_near_term_draft_rows(draft_rows)

    assert summary["has_changes"] is True
    assert summary["changed_day_count"] == 2
    assert summary["off_day_count"] >= 1
    assert summary["quality_day_count"] >= 1
    assert summary["total_delta_tss"] != 0
    assert summary["changed_rows"][0]["День"].startswith("Пн")
    assert summary["changed_rows"][0]["Станет"]
    assert summary["changed_rows"][0]["Δ TSS"].startswith(("+", "-"))


def test_build_near_term_edit_seed_from_goal_plans_projects_target_variant():
    goal_plan = _sample_goal_plan()
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)
    target_goal_plan = apply_near_term_day_edits(
        goal_plan,
        [
            {
                **edit_rows[1],
                "session_role": "off",
                "sport": "off",
                "total_tss": 0,
            }
        ],
        horizon_days=7,
        post_edit_strategy="protect_recovery",
    )

    seed = build_near_term_edit_seed_from_goal_plans(
        goal_plan,
        target_goal_plan,
        horizon_days=7,
        post_edit_strategy="protect_recovery",
        source_label="Execution microcycle",
    )

    assert seed is not None
    assert seed["source_label"] == "Execution microcycle"
    assert seed["post_edit_strategy"] == "protect_recovery"
    assert seed["draft_summary"]["has_changes"] is True
    assert seed["draft_summary"]["changed_day_count"] >= 1
    assert seed["overrides_by_index"][1]["session_role"] == "off"
    assert seed["overrides_by_index"][1]["sport"] == "off"
    assert seed["overrides_by_index"][1]["total_tss"] == 0.0


def test_apply_near_term_day_edits_preserves_existing_mix_when_sport_is_unchanged():
    goal_plan = _sample_goal_plan()
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)
    original_parts = goal_plan["daily_plan"][1][2]

    updated_goal_plan = apply_near_term_day_edits(
        goal_plan,
        [
            {
                **edit_rows[1],
                "session_role": edit_rows[1]["current_role"],
                "sport": edit_rows[1]["current_sport"],
                "total_tss": 80,
            }
        ],
        horizon_days=7,
    )

    updated_parts = updated_goal_plan["daily_plan"][1][2]

    assert round(sum(updated_parts.values()), 1) == 80.0
    assert set(updated_parts.keys()) == set(original_parts.keys())
    assert sum(1 for value in updated_parts.values() if value > 0) >= 1


def test_apply_near_term_day_edits_updates_checkpoint_totals():
    goal_plan = _sample_goal_plan()
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)

    updated_goal_plan = apply_near_term_day_edits(
        goal_plan,
        [
            {
                **edit_rows[2],
                "session_role": "long",
                "sport": edit_rows[2]["current_sport"],
                "total_tss": edit_rows[2]["current_total_tss"] + 20,
            }
        ],
        horizon_days=7,
    )
    checkpoint = build_planning_checkpoint(updated_goal_plan)

    assert checkpoint["total_tss"] == sum(updated_goal_plan["weekly_tss_plan"])
    assert checkpoint["peak_tss"] == max(updated_goal_plan["weekly_tss_plan"])
    assert checkpoint["goal_plan_snapshot"]["constraint_summary"]["near_term_edit"]["is_active"] is True


def test_apply_near_term_day_edits_can_return_removed_load_into_next_weeks():
    goal_plan = _sample_goal_plan()
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)
    original_week_two_total = goal_plan["weekly_tss_plan"][1]

    updated_goal_plan = apply_near_term_day_edits(
        goal_plan,
        [
            {
                **edit_rows[1],
                "session_role": "off",
                "sport": "off",
                "total_tss": 0,
            }
        ],
        horizon_days=7,
        post_edit_strategy="catch_up",
    )

    near_term_edit = updated_goal_plan["constraint_summary"]["near_term_edit"]

    assert near_term_edit["post_edit_strategy"] == "catch_up"
    assert near_term_edit["future_target_tss"] > 0
    assert near_term_edit["future_delta_tss"] > 0
    assert near_term_edit["risk_level"] == "low"
    assert updated_goal_plan["weekly_tss_plan"][1] > original_week_two_total
    assert "ручной возврат" in updated_goal_plan["weekly_summary"][1]["adjustment_note"]
    assert any("вернула" in note for note in updated_goal_plan["constraint_summary"]["notes"])


def test_apply_near_term_day_edits_can_soften_following_weeks_after_manual_overload():
    goal_plan = _sample_goal_plan()
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)
    original_week_two_total = goal_plan["weekly_tss_plan"][1]

    updated_goal_plan = apply_near_term_day_edits(
        goal_plan,
        [
            {
                **edit_rows[1],
                "session_role": edit_rows[1]["current_role"],
                "sport": edit_rows[1]["current_sport"],
                "total_tss": edit_rows[1]["current_total_tss"] + 40,
            }
        ],
        horizon_days=7,
        post_edit_strategy="protect_recovery",
    )

    near_term_edit = updated_goal_plan["constraint_summary"]["near_term_edit"]

    assert near_term_edit["post_edit_strategy"] == "protect_recovery"
    assert near_term_edit["future_target_tss"] < 0
    assert near_term_edit["future_delta_tss"] < 0
    assert near_term_edit["risk_level"] == "medium"
    assert updated_goal_plan["weekly_tss_plan"][1] < original_week_two_total
    assert "ручная разгрузка" in updated_goal_plan["weekly_summary"][1]["adjustment_note"]
    assert any("сняла" in note for note in updated_goal_plan["constraint_summary"]["notes"])


def test_apply_near_term_day_edits_marks_aggressive_manual_overload_as_high_risk():
    goal_plan = _sample_goal_plan()
    goal_plan["constraint_summary"]["current_tsb"] = -18.0
    goal_plan["constraint_summary"]["load_state"] = "fatigued"
    goal_plan["constraint_summary"]["load_state_label"] = "Накопленная усталость"
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)

    updated_goal_plan = apply_near_term_day_edits(
        goal_plan,
        [
            {
                **edit_rows[0],
                "session_role": "quality",
                "sport": "run",
                "total_tss": 95,
            },
            {
                **edit_rows[1],
                "session_role": "quality",
                "sport": "run",
                "total_tss": edit_rows[1]["current_total_tss"] + 35,
            },
        ],
        horizon_days=7,
        post_edit_strategy="keep",
    )

    near_term_edit = updated_goal_plan["constraint_summary"]["near_term_edit"]

    assert near_term_edit["risk_level"] == "high"
    assert near_term_edit["risk_focus"] == "overload"
    assert any("устал" in reason for reason in near_term_edit["risk_reasons"])
    assert "Верните" in near_term_edit["risk_guardrail"]


def test_build_safer_near_term_draft_softens_high_risk_overload_and_switches_strategy():
    goal_plan = _sample_goal_plan()
    goal_plan["constraint_summary"]["current_tsb"] = -18.0
    goal_plan["constraint_summary"]["load_state"] = "fatigued"
    goal_plan["constraint_summary"]["load_state_label"] = "Накопленная усталость"
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)
    draft_rows = build_near_term_edit_draft_rows(
        edit_rows,
        goal_type=goal_plan["goal_type"],
        distance=goal_plan["distance"],
        overrides_by_index={
            int(edit_rows[0]["index"]): {
                "session_role": "quality",
                "sport": "run",
                "total_tss": 95,
            },
            int(edit_rows[1]["index"]): {
                "session_role": "quality",
                "sport": "run",
                "total_tss": edit_rows[1]["current_total_tss"] + 35,
            },
        },
    )

    safer_draft = build_safer_near_term_draft(
        goal_plan,
        draft_rows,
        horizon_days=7,
        post_edit_strategy="keep",
    )

    assert safer_draft is not None
    assert safer_draft["post_edit_strategy"] == "protect_recovery"
    assert safer_draft["near_term_edit"]["risk_level"] in {"low", "medium"}
    assert safer_draft["near_term_edit"]["risk_level"] != "high"
    assert safer_draft["draft_summary"]["changed_day_count"] >= 1
    assert any("стратегию" in action or "снизить" in action or "вернуть" in action for action in safer_draft["actions"])


def test_build_safer_near_term_draft_returns_none_for_low_risk_cutback():
    goal_plan = _sample_goal_plan()
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)
    draft_rows = build_near_term_edit_draft_rows(
        edit_rows,
        goal_type=goal_plan["goal_type"],
        distance=goal_plan["distance"],
        overrides_by_index={
            int(edit_rows[1]["index"]): {
                "session_role": "off",
                "sport": "off",
                "total_tss": 0,
            }
        },
    )

    safer_draft = build_safer_near_term_draft(
        goal_plan,
        draft_rows,
        horizon_days=7,
        post_edit_strategy="catch_up",
    )

    assert safer_draft is None

from __future__ import annotations

from datetime import date

import pytest

from data.database import Database
from models.planning_checkpoints import (
    build_planning_checkpoint,
    checkpoint_to_goal_plan_context,
    get_near_term_edit_rollback_target_checkpoint_id,
    resolve_goal_plan_context,
    restore_goal_plan_from_checkpoint,
    summarize_checkpoint_provenance,
    summarize_execution_feedback_transition,
    summarize_planning_checkpoint,
    with_checkpoint_provenance,
)
from models.planning_execution import rebuild_goal_plan_with_adjustment
from models.training_planner import build_daily_session_templates, expand_weekly_to_daily_triathlon


pytestmark = pytest.mark.smoke


def _sample_goal_plan() -> dict[str, object]:
    daily_plan, _generated_weekly_summary = expand_weekly_to_daily_triathlon(
        [180, 220, 240],
        ["Base", "Build", "Peak"],
        "Олимпийка",
        date(2026, 6, 15),
        goal_type="Триатлон",
        load_state="fatigued",
    )
    session_templates = build_daily_session_templates(
        daily_plan,
        _generated_weekly_summary,
        "Триатлон",
        "Олимпийка",
    )
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "weeks_to_race": 8,
        "start_week": date(2026, 6, 15),
        "weekly_tss_plan": [180, 220, 240],
        "base_weekly_tss_plan": [240, 240, 240],
        "phases": ["Base", "Build", "Peak"],
        "daily_plan": daily_plan,
        "session_templates": session_templates,
        "planner_mix": {
            "Base": {"run": 0.35, "bike": 0.47, "swim": 0.18},
            "Build": {"run": 0.37, "bike": 0.45, "swim": 0.18},
            "Peak": {"run": 0.37, "bike": 0.45, "swim": 0.18},
        },
        "planner_weights": {
            "Base": {
                "run": [0.10, 0.18, 0.15, 0.07, 0.22, 0.18, 0.10],
                "bike": [0.10, 0.15, 0.20, 0.05, 0.25, 0.15, 0.10],
                "swim": [0.15, 0.15, 0.20, 0.10, 0.15, 0.15, 0.10],
            }
        },
        "weekly_summary": [
            {
                "week_start": date(2026, 6, 15),
                "phase": "Base",
                "weekly_tss": 180,
                "capacity_tss": 220,
                "adjustment_note": "checkpoint: пропущено 2 сесс. → 65%",
                "structure_summary": "1 качеств. дн., 1 восстановит. дн., длительная: Сб",
            },
            {
                "week_start": date(2026, 6, 22),
                "phase": "Build",
                "weekly_tss": 220,
                "capacity_tss": 220,
                "adjustment_note": "локальный возврат +20 TSS",
                "structure_summary": "",
            },
        ],
        "constraint_summary": {
            "available_hours": 8.5,
            "available_day_indices": [1, 3, 5],
            "available_day_labels": ["Вт", "Чт", "Сб"],
            "available_day_count": 3,
            "recommended_days": 6,
            "interruption_type": "none",
            "interruption_label": "Нет",
            "interruption_weeks": 0,
            "catch_up_strategy": "catch_up",
            "plan_adjustment": {
                "status": "skipped",
                "label": "Пропущены сессии",
                "weeks": 1,
            },
            "plan_adjustment_recovered_tss": 20,
            "near_term_edit": {
                "is_active": True,
                "edited_day_count": 3,
                "horizon_days": 7,
                "total_delta_tss": -15,
                "label": "Ручная правка ближнего горизонта",
                "post_edit_strategy": "catch_up",
                "future_target_tss": 10,
                "future_delta_tss": 10,
                "future_weeks": 2,
                "future_week_count": 1,
            },
            "current_tsb": -12.0,
            "current_ctl": 55.0,
            "current_atl": 68.0,
            "load_state_label": "Накопленная усталость",
            "notes": [
                "Checkpoint: Пропущены сессии на 1 нед.",
                "Локальная перепланировка вернула 20 из 25 TSS в ближайшем окне",
            ],
        },
        "plan_revision": "2026-06-15T08:00:00",
        "near_term_edit_version": 1,
        "near_term_edit_horizon_days": 7,
        "near_term_edit_rollback_target_checkpoint_id": 41,
        "checkpoint_source": "manual_edit",
        "checkpoint_parent_id": 40,
        "checkpoint_restored_from_checkpoint_id": None,
    }


def test_database_roundtrips_planning_checkpoint(tmp_path):
    db = Database(str(tmp_path / "planning_checkpoints.db"))
    checkpoint = build_planning_checkpoint(_sample_goal_plan())

    saved = db.save_planning_checkpoint(checkpoint)
    latest = db.get_latest_planning_checkpoint()
    history = db.get_recent_planning_checkpoints(limit=3)
    fetched = db.get_planning_checkpoint(saved["id"])

    assert saved["id"]
    assert fetched["id"] == saved["id"]
    assert latest["goal_type"] == "Триатлон"
    assert latest["goal_plan_snapshot"]["constraint_summary"]["plan_adjustment"]["label"] == "Пропущены сессии"
    assert latest["goal_plan_snapshot"]["daily_plan"]
    assert latest["goal_plan_snapshot"]["weekly_summary"][0]["adjustment_note"].startswith("checkpoint:")
    assert len(history) == 1


def test_checkpoint_helpers_restore_goal_plan_context():
    checkpoint = build_planning_checkpoint(_sample_goal_plan())

    restored = checkpoint_to_goal_plan_context(checkpoint)
    restored_full = restore_goal_plan_from_checkpoint(checkpoint)
    resolved = resolve_goal_plan_context(None, checkpoint)
    summary = summarize_planning_checkpoint(checkpoint)

    assert restored["constraint_summary"]["available_day_labels"] == ["Вт", "Чт", "Сб"]
    assert restored["start_week"] == date(2026, 6, 15)
    assert restored["weekly_summary"][0]["week_start"] == date(2026, 6, 15)
    assert len(restored["daily_plan"]) == len(_sample_goal_plan()["daily_plan"])
    assert restored_full is not None
    assert len(restored_full["session_templates"]) == len(_sample_goal_plan()["session_templates"])
    assert get_near_term_edit_rollback_target_checkpoint_id(checkpoint) == 41
    assert resolved["constraint_summary"]["plan_adjustment"]["label"] == "Пропущены сессии"
    assert summary["plan_adjustment_label"] == "Пропущены сессии"
    assert summary["checkpoint_id"] is None
    assert summary["peak_tss"] == 240
    assert summary["provenance"]["source"] == "manual_edit"
    assert summary["provenance"]["label"] == "Ручная правка"
    assert "3 дн." in summary["provenance"]["detail"]
    assert summary["near_term_edit"]["edited_day_count"] == 3
    assert summary["near_term_edit"]["total_delta_tss"] == -15
    assert summary["near_term_edit"]["strategy_label"] == "Наверстать аккуратно"
    assert summary["near_term_edit"]["future_delta_tss"] == 10
    assert summary["near_term_edit"]["risk_level"] == "low"
    assert checkpoint["near_term_edit_risk_level"] == "low"


def test_restore_goal_plan_from_legacy_checkpoint_rebuilds_daily_details():
    legacy_goal_plan = dict(_sample_goal_plan())
    legacy_goal_plan.pop("daily_plan", None)
    legacy_goal_plan.pop("session_templates", None)
    checkpoint = build_planning_checkpoint(legacy_goal_plan)

    restored = restore_goal_plan_from_checkpoint(checkpoint)

    assert restored is not None
    assert restored["daily_plan"]
    assert restored["session_templates"]
    assert restored["weekly_tss_plan"] == legacy_goal_plan["weekly_tss_plan"]


def test_summarize_checkpoint_provenance_describes_restored_version():
    restored_goal_plan = with_checkpoint_provenance(
        _sample_goal_plan(),
        source="restore_version",
        parent_checkpoint_id=55,
        restored_from_checkpoint_id=41,
    )
    checkpoint = build_planning_checkpoint(restored_goal_plan)

    provenance = summarize_checkpoint_provenance(checkpoint)

    assert provenance is not None
    assert provenance["source"] == "restore_version"
    assert provenance["parent_checkpoint_id"] == 55
    assert provenance["restored_from_checkpoint_id"] == 41
    assert provenance["detail"] == "Восстановлен checkpoint #41"


def test_rebuild_goal_plan_with_adjustment_from_checkpoint_context():
    checkpoint = build_planning_checkpoint(_sample_goal_plan())
    restored = checkpoint_to_goal_plan_context(checkpoint)

    rebuilt = rebuild_goal_plan_with_adjustment(
        restored,
        {
            "status": "reduced",
            "weeks": 1,
            "reduced_load_share": 0.60,
        },
    )

    assert rebuilt["start_week"] == date(2026, 6, 15)
    assert rebuilt["constraint_summary"]["plan_adjustment"]["label"] == "Нагрузка урезана"
    assert rebuilt["constraint_summary"]["plan_adjustment"]["weeks"] == 1
    assert rebuilt["weekly_tss_plan"][0] < rebuilt["base_weekly_tss_plan"][0]
    assert "checkpoint:" in rebuilt["weekly_summary"][0]["adjustment_note"]
    assert len(rebuilt["session_templates"]) == len(rebuilt["daily_plan"])


def test_execution_feedback_summary_ignores_manual_edit_checkpoint_versions():
    checkpoint = build_planning_checkpoint(_sample_goal_plan())

    summary = summarize_execution_feedback_transition(None, checkpoint)

    assert summary is None


def test_summarize_execution_feedback_transition_from_persisted_checkpoints():
    previous_checkpoint = build_planning_checkpoint(_sample_goal_plan())
    rebuilt = rebuild_goal_plan_with_adjustment(
        checkpoint_to_goal_plan_context(previous_checkpoint),
        {
            "status": "reduced",
            "weeks": 1,
            "reduced_load_share": 0.60,
        },
    )
    current_checkpoint = build_planning_checkpoint(
        with_checkpoint_provenance(
            rebuilt,
            source="execution_feedback",
            parent_checkpoint_id=previous_checkpoint["id"] if "id" in previous_checkpoint else None,
        )
    )

    summary = summarize_execution_feedback_transition(
        previous_checkpoint,
        current_checkpoint,
    )

    assert summary is not None
    assert summary["plan_adjustment_label"] == "Нагрузка урезана"
    assert summary["total_delta"] < 0
    assert summary["peak_delta"] <= 0

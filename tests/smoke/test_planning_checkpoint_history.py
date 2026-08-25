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
from models.planning_execution import (
    build_execution_plan_adjustment,
    build_execution_reconciliation_rows,
    rebuild_goal_plan_with_adjustment,
)
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
        "event_date": "2026-08-10",
        "events": [
            {"date": "2026-08-10", "priority": "A", "label": "Триатлон Олимпийка"},
            {"date": "2026-07-20", "priority": "B", "label": "Контрольный старт"},
        ],
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
                "execution_adaptation_pressure": {
                    "level": "medium",
                    "score": 40,
                    "follow_up_mode": "hold",
                    "follow_up_label": "Удержать текущий потолок",
                    "rebuild_horizon_weeks": 2,
                    "growth_cap_tss_per_week": 25,
                    "recovery_share_cap": 0.0,
                    "reason": "Окно уже сдвинулось заметно: следующие 1-2 недели лучше удержать текущий потолок.",
                },
                "execution_weekly_review": {
                    "headline": "Пропущена ключевая сессия",
                    "review_badge": "Потеря качества",
                    "deviations": [
                        {
                            "code": "missed_key_session",
                            "label": "Пропущена ключевая сессия",
                            "detail": "Триатлон Олимпийка — Качество • бег",
                        }
                    ],
                    "recommended_response_strategy": "protect_recovery",
                    "recommended_response_label": "Беречь восстановление",
                    "recommended_response_reason": "После пропуска ключевой работы важнее вернуть структуру недели.",
                    "selected_response_strategy": "catch_up",
                    "selected_response_label": "Наверстать аккуратно",
                },
                "execution_corrective_microcycle": {
                    "headline": "Ближайшие 2-3 дня: вернуть структуру без второй quality-сессии",
                    "summary": "Следующее окно сохраняет один качественный стимул и не добирает пропущенную интенсивность сверху.",
                    "today_action": "Thu 18.06: Сделать контролируемо — Триатлон Олимпийка — Качество • бег (35 TSS).",
                    "next_window": "Fri 19.06: Оставить лёгкой (Триатлон Олимпийка — Легкая • бег)",
                    "guardrail": "Не добавляйте вторую интенсивную работу рядом с текущей ключевой сессией.",
                    "selected_response_strategy": "catch_up",
                    "selected_response_label": "Наверстать аккуратно",
                    "window_total_tss": 80,
                    "window_delta_tss": -10,
                    "window_day_count": 2,
                    "sessions": [
                        {
                            "date": "2026-06-18",
                            "date_label": "Thu 18.06",
                            "session_name": "Триатлон Олимпийка — Качество • бег",
                            "session_role": "quality",
                            "session_role_label": "Качество",
                            "planned_total_tss": 35,
                            "planned_duration_minutes": 60,
                            "delta_tss": -10,
                            "delta_label": "-10 TSS",
                            "action_code": "controlled_quality",
                            "action_label": "Сделать контролируемо",
                            "reason": "Верните структуру недели, но не пытайтесь добрать выпавшую интенсивность внутри этой сессии.",
                        }
                    ],
                },
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
                "origin_kind": "execution_microcycle_override",
                "origin_checkpoint_id": 40,
                "origin_checkpoint_source": "execution_feedback",
                "origin_plan_adjustment_label": "Пропущены сессии",
                "origin_weekly_review_headline": "Пропущена ключевая сессия",
                "origin_microcycle_headline": "Ближайшие 2-3 дня: вернуть структуру без второй quality-сессии",
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
    session_id = saved["goal_plan_snapshot"]["session_templates"][0]["sessions"][0][
        "session_id"
    ]
    matching = db.get_planning_checkpoints_for_session(session_id)

    assert saved["id"]
    assert fetched["id"] == saved["id"]
    assert latest["goal_type"] == "Триатлон"
    assert latest["goal_plan_snapshot"]["constraint_summary"]["plan_adjustment"]["label"] == "Пропущены сессии"
    assert latest["goal_plan_snapshot"]["daily_plan"]
    assert latest["goal_plan_snapshot"]["weekly_summary"][0]["adjustment_note"].startswith("checkpoint:")
    assert len(history) == 1
    assert [item["id"] for item in matching] == [saved["id"]]


def test_checkpoint_helpers_restore_goal_plan_context():
    checkpoint = build_planning_checkpoint(_sample_goal_plan())

    restored = checkpoint_to_goal_plan_context(checkpoint)
    restored_full = restore_goal_plan_from_checkpoint(checkpoint)
    resolved = resolve_goal_plan_context(None, checkpoint)
    summary = summarize_planning_checkpoint(checkpoint)

    assert checkpoint["event_date"] == "2026-08-10"
    assert checkpoint["events"] == _sample_goal_plan()["events"]
    assert checkpoint["goal_plan_snapshot"]["event_date"] == "2026-08-10"
    assert checkpoint["goal_plan_snapshot"]["events"] == _sample_goal_plan()["events"]
    assert restored["event_date"] == "2026-08-10"
    assert restored["events"] == _sample_goal_plan()["events"]
    assert restored["constraint_summary"]["available_day_labels"] == ["Вт", "Чт", "Сб"]
    assert restored["start_week"] == date(2026, 6, 15)
    assert restored["weekly_summary"][0]["week_start"] == date(2026, 6, 15)
    assert len(restored["daily_plan"]) == len(_sample_goal_plan()["daily_plan"])
    assert restored_full is not None
    assert restored_full["event_date"] == "2026-08-10"
    assert len(restored_full["session_templates"]) == len(_sample_goal_plan()["session_templates"])
    assert get_near_term_edit_rollback_target_checkpoint_id(checkpoint) == 41
    assert resolved["event_date"] == "2026-08-10"
    assert resolved["constraint_summary"]["plan_adjustment"]["label"] == "Пропущены сессии"
    assert summary["plan_adjustment_label"] == "Пропущены сессии"
    assert summary["checkpoint_id"] is None
    assert summary["peak_tss"] == 240
    assert summary["provenance"]["source"] == "manual_edit"
    assert summary["provenance"]["label"] == "Ручная правка"
    assert "3 дн." in summary["provenance"]["detail"]
    assert "Override после execution microcycle" in summary["provenance"]["detail"]
    assert summary["near_term_edit"]["edited_day_count"] == 3
    assert summary["near_term_edit"]["total_delta_tss"] == -15
    assert summary["near_term_edit"]["strategy_label"] == "Наверстать аккуратно"
    assert summary["near_term_edit"]["future_delta_tss"] == 10
    assert summary["near_term_edit"]["risk_level"] == "low"
    assert summary["near_term_edit"]["origin_checkpoint_id"] == 40
    assert summary["near_term_edit"]["origin_label"].startswith("Override после execution microcycle")
    assert "Пропущены сессии" in summary["near_term_edit"]["origin_description"]
    assert summary["execution_weekly_review"]["headline"] == "Пропущена ключевая сессия"
    assert summary["execution_weekly_review"]["selected_response_label"] == "Наверстать аккуратно"
    assert summary["execution_corrective_microcycle"]["headline"].startswith("Ближайшие 2-3 дня")
    assert summary["execution_corrective_microcycle"]["sessions"][0]["action_label"] == "Сделать контролируемо"
    assert summary["execution_adaptation_pressure"]["follow_up_mode"] == "hold"
    assert summary["execution_adaptation_pressure"]["follow_up_label"] == "Удержать текущий потолок"
    assert checkpoint["near_term_edit_risk_level"] == "low"
    assert checkpoint["execution_adaptation_pressure_level"] == "medium"


def test_restore_legacy_event_date_synthesizes_primary_a_event():
    checkpoint = build_planning_checkpoint(_sample_goal_plan())
    checkpoint["events"] = []
    checkpoint["goal_plan_snapshot"].pop("events", None)

    restored = restore_goal_plan_from_checkpoint(checkpoint)

    assert restored is not None
    assert restored["event_date"] == "2026-08-10"
    assert restored["events"] == [
        {
            "date": "2026-08-10",
            "priority": "A",
            "label": "Триатлон Олимпийка",
            "source": "legacy_checkpoint",
            "priority_provenance": "legacy_assumed",
            "confirmed": False,
            "requires_confirmation": True,
        }
    ]


def test_checkpoint_round_trip_preserves_planning_mode_and_overlay_provenance():
    plan = _sample_goal_plan()
    plan.update(
        {
            "planning_mode": "event_goal",
            "planning_intent": "develop",
            "planning_focus": "balanced_triathlon",
            "macrocycle_event_date": "2026-08-10",
            "overlay_rule_version": "race-overlay-v1",
            "event_overlays": [
                {"date": "2026-07-12", "priority": "B", "affected_dates": ["2026-07-12"]}
            ],
            "microcycle_changes": [
                {
                    "date": "2026-07-11",
                    "event_date": "2026-07-12",
                    "priority": "B",
                    "offset": -1,
                    "phase": "Peak",
                    "before": {"role": "long", "sport": "bike", "focus": "Long", "tss": 40.0},
                    "after": {"role": "activation", "sport": "run", "focus": "Activation", "tss": 10.0},
                }
            ],
            "protected_dates": ["2026-07-12", "2026-07-13"],
        }
    )

    restored = restore_goal_plan_from_checkpoint(build_planning_checkpoint(plan))

    assert restored is not None
    assert restored["planning_mode"] == "event_goal"
    assert restored["macrocycle_event_date"] == "2026-08-10"
    assert restored["overlay_rule_version"] == "race-overlay-v1"
    assert restored["microcycle_changes"][0]["after"]["role"] == "activation"
    assert restored["protected_dates"] == ["2026-07-12", "2026-07-13"]


def test_resolve_current_goal_plan_derives_alias_from_events():
    resolved = resolve_goal_plan_context(
        {
            "event_date": "2026-09-01",
            "events": [{"date": "2026-08-10", "priority": "B", "label": "Подводящий старт"}],
        },
        None,
    )

    assert resolved is not None
    assert resolved["event_date"] == "2026-08-10"


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
    assert rebuilt["event_date"] == "2026-08-10"
    assert rebuilt["events"] == _sample_goal_plan()["events"]
    assert rebuilt["constraint_summary"]["plan_adjustment"]["label"] == "Нагрузка урезана"
    assert rebuilt["constraint_summary"]["plan_adjustment"]["weeks"] == 1
    assert rebuilt["weekly_tss_plan"][0] < rebuilt["base_weekly_tss_plan"][0]
    assert "checkpoint:" in rebuilt["weekly_summary"][0]["adjustment_note"]
    assert len(rebuilt["session_templates"]) == len(rebuilt["daily_plan"])


def test_execution_rebuild_reapplies_race_protection_and_mode_metadata():
    plan = _sample_goal_plan()
    event_date = "2026-06-20"
    plan.update(
        {
            "planning_mode": "training_goal",
            "planning_intent": "develop",
            "events": [{"date": event_date, "priority": "B", "label": "B race", "confirmed": True}],
            "event_date": "",
            "macrocycle_event_date": "",
        }
    )

    rebuilt = rebuild_goal_plan_with_adjustment(
        plan,
        {"status": "as_planned", "weeks": 0},
    )
    by_date = {row[0].date().isoformat(): row for row in rebuilt["daily_plan"]}

    assert rebuilt["planning_mode"] == "training_goal"
    assert rebuilt["event_date"] == ""
    assert rebuilt["overlay_rule_version"] == "race-microcycle-v2"
    assert rebuilt["microcycle_changes"]
    assert by_date[event_date][1] == 0
    assert event_date in rebuilt["protected_dates"]


def test_execution_feedback_summary_ignores_manual_edit_checkpoint_versions():
    checkpoint = build_planning_checkpoint(_sample_goal_plan())

    summary = summarize_execution_feedback_transition(None, checkpoint)

    assert summary is None


def test_summarize_execution_feedback_transition_from_persisted_checkpoints():
    previous_checkpoint = build_planning_checkpoint(_sample_goal_plan())
    execution_rows = build_execution_reconciliation_rows(
        checkpoint_to_goal_plan_context(previous_checkpoint),
        weeks=1,
    )
    positive_rows = [
        index
        for index, row in enumerate(execution_rows)
        if int(row.get("planned_total_tss", 0) or 0) > 0
    ]
    execution_rows[positive_rows[0]]["outcome"] = "missed"
    execution_rows[positive_rows[1]]["outcome"] = "reduced"
    execution_rows[positive_rows[1]]["actual_total_tss"] = max(
        0,
        int(execution_rows[positive_rows[1]]["planned_total_tss"]) - 10,
    )
    rebuilt = rebuild_goal_plan_with_adjustment(
        checkpoint_to_goal_plan_context(previous_checkpoint),
        build_execution_plan_adjustment(
            checkpoint_to_goal_plan_context(previous_checkpoint),
            execution_rows,
            weeks=1,
        ),
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
    assert summary["execution_reconciliation"] is not None
    assert summary["execution_reconciliation"]["changed_day_count"] == 2
    assert summary["execution_weekly_review"] is not None
    assert summary["execution_weekly_review"]["headline"]
    assert summary["execution_corrective_microcycle"] is not None
    assert summary["execution_corrective_microcycle"]["today_action"]

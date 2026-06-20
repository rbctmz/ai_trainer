from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from models.planning_near_term import (
    apply_near_term_day_edits,
    build_near_term_edit_draft_rows,
    build_near_term_edit_rows,
)
from models.training_planner import build_daily_session_templates, expand_weekly_to_daily_triathlon
from ui.pages.planning import (
    _align_slider_value,
    _build_daily_session_rows,
    _build_plan_fact_focus_action,
    _build_plan_fact_calendar_markup,
    _build_plan_fact_calendar_rows,
    _build_plan_fact_week_summary,
    _build_goal_plan_transition_preview,
    _build_near_term_draft_preview,
    _build_plan_explainability,
    _normalize_planning_workspace_mode,
    _resolve_plan_fact_calendar_default_week,
    _resolve_planning_start_week,
    _resolve_near_term_tss_widget_max,
    _resolve_target_weekly_tss_control,
    _resolve_target_weekly_tss_step,
)


pytestmark = pytest.mark.smoke


def test_build_plan_explainability_summarizes_adaptive_changes():
    explain = _build_plan_explainability(
        {
            "weekly_tss_plan": [180, 220, 240],
            "base_weekly_tss_plan": [240, 240, 240],
            "phases": ["Base", "Build", "Peak"],
            "weekly_summary": [
                {
                    "week_start": date(2026, 6, 15),
                    "adjustment_note": "потолок 220 TSS",
                    "structure_summary": "1 качеств. дн., 1 восстановит. дн., длительная: Сб",
                },
                {"week_start": date(2026, 6, 22), "adjustment_note": "возврат +20 TSS"},
                {"week_start": date(2026, 6, 29), "adjustment_note": "—"},
            ],
            "constraint_summary": {
                "weekly_capacity_tss": 220,
                "available_hours": 8.5,
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "available_day_count": 3,
                "recommended_days": 6,
                "interruption_label": "Отпуск",
                "interruption_weeks": 1,
                "catch_up_strategy": "catch_up",
                "recovered_tss": 20,
                "capacity_loss_tss": 60,
                "interruption_loss_tss": 40,
                "notes": ["Отпуск на 1 нед.", "Стратегия «Наверстать аккуратно» вернула 20 из 25 TSS"],
            },
        }
    )

    assert explain["headline"].startswith("План сначала снижает нагрузку")
    assert explain["summary_notes"][0].startswith("Структура первой недели:")
    assert explain["peak_before"] == 240
    assert explain["peak_after"] == 240
    assert explain["total_delta"] == -80
    assert explain["changed_weeks"] == 2
    assert explain["availability_days"] == "Вт, Чт, Сб"
    assert explain["catch_up_label"] == "Наверстать аккуратно"
    assert explain["comparison_rows"][0]["Базовый TSS"] == 240
    assert explain["comparison_rows"][1]["Почему"] == "возврат +20 TSS"


def test_build_plan_explainability_detects_nearly_unchanged_plan():
    explain = _build_plan_explainability(
        {
            "weekly_tss_plan": [180, 200],
            "base_weekly_tss_plan": [180, 200],
            "phases": ["Base", "Build"],
            "weekly_summary": [
                {"week_start": date(2026, 7, 6), "adjustment_note": "—"},
                {"week_start": date(2026, 7, 13), "adjustment_note": "—"},
            ],
            "constraint_summary": {
                "weekly_capacity_tss": 220,
                "available_hours": 10.0,
                "available_day_labels": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"],
                "available_day_count": 6,
                "recommended_days": 6,
                "interruption_label": "Нет",
                "interruption_weeks": 0,
                "catch_up_strategy": "protect_recovery",
                "recovered_tss": 0,
                "capacity_loss_tss": 0,
                "interruption_loss_tss": 0,
                "notes": [],
            },
        }
    )

    assert "почти не менять базовый план" in explain["headline"]
    assert explain["changed_weeks"] == 0
    assert explain["total_delta"] == 0


def test_build_plan_explainability_prioritizes_local_replan_story():
    explain = _build_plan_explainability(
        {
            "weekly_tss_plan": [130, 215, 215, 180],
            "base_weekly_tss_plan": [200, 200, 200, 180],
            "phases": ["Base", "Build", "Build", "Taper"],
            "weekly_summary": [
                {"week_start": date(2026, 7, 6), "adjustment_note": "checkpoint: пропущено 2 сесс. → 65%"},
                {"week_start": date(2026, 7, 13), "adjustment_note": "локальный возврат +15 TSS"},
                {"week_start": date(2026, 7, 20), "adjustment_note": "локальный возврат +15 TSS"},
                {"week_start": date(2026, 7, 27), "adjustment_note": "—"},
            ],
            "constraint_summary": {
                "weekly_capacity_tss": 500,
                "available_hours": 10.0,
                "available_day_labels": ["Пн", "Вт", "Ср", "Чт", "Пт"],
                "available_day_count": 5,
                "recommended_days": 5,
                "interruption_label": "Нет",
                "interruption_weeks": 0,
                "catch_up_strategy": "catch_up",
                "recovered_tss": 0,
                "capacity_loss_tss": 0,
                "interruption_loss_tss": 0,
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
                    "execution_corrective_microcycle": {
                        "headline": "Ближайшие 2-3 дня: вернуть структуру без второй quality-сессии",
                        "today_action": "Thu 18.06: Сделать контролируемо — Триатлон Олимпийка — Качество • бег (35 TSS).",
                        "next_window": "Fri 19.06: Оставить лёгкой (Триатлон Олимпийка — Легкая • бег)",
                        "guardrail": "Не добавляйте вторую интенсивную работу рядом с текущей ключевой сессией.",
                        "sessions": [
                            {
                                "action_label": "Сделать контролируемо",
                                "session_name": "Триатлон Олимпийка — Качество • бег",
                            }
                        ],
                    },
                },
                "plan_adjustment_loss_tss": 70,
                "plan_adjustment_recovered_tss": 30,
                "notes": ["Checkpoint: Пропущены сессии на 1 нед."],
            },
        }
    )

    assert explain["headline"].startswith("План локально пересчитывает ближайшие недели")
    assert explain["plan_adjustment_label"] == "Пропущены сессии"
    assert explain["plan_adjustment_weeks"] == 1
    assert explain["plan_adjustment_loss_tss"] == 70
    assert explain["plan_adjustment_recovered_tss"] == 30
    assert explain["execution_corrective_microcycle"] is not None
    assert explain["execution_adaptation_pressure"] is not None
    assert explain["execution_adaptation_pressure"]["follow_up_mode"] == "hold"
    assert "не расти быстрее +25 TSS/нед." in explain["execution_adaptation_pressure"]["follow_up_window_description"]
    assert explain["execution_corrective_microcycle"]["headline"].startswith("Ближайшие 2-3 дня")
    assert explain["execution_corrective_microcycle"]["today_action"].startswith("Thu 18.06")
    assert explain["comparison_rows"][1]["Почему"] == "локальный возврат +15 TSS"


def test_target_tss_control_avoids_equal_slider_bounds():
    control = _resolve_target_weekly_tss_control(
        auto_suggested=500,
        t_min=500,
        t_max=700,
        availability_cap_tss=500,
    )

    assert control["is_fixed"] is True
    assert control["value"] == 500
    assert control["reason"] == "single_value"


def test_target_tss_control_can_lock_to_achievable_cap_below_goal_floor():
    control = _resolve_target_weekly_tss_control(
        auto_suggested=620,
        t_min=500,
        t_max=700,
        availability_cap_tss=400,
    )

    assert control["is_fixed"] is True
    assert control["value"] == 400
    assert control["reason"] == "availability_cap"


def test_target_tss_slider_step_softens_for_narrow_ranges():
    assert _resolve_target_weekly_tss_step(500, 505) == 1
    assert _resolve_target_weekly_tss_step(500, 520) == 5
    assert _resolve_target_weekly_tss_step(500, 600) == 25


def test_align_slider_value_clamps_to_valid_step():
    assert _align_slider_value(107, min_value=0, max_value=1000, step=50) == 100
    assert _align_slider_value(149, min_value=0, max_value=1000, step=50) == 150
    assert _align_slider_value(1015, min_value=0, max_value=1000, step=50) == 1000


def test_near_term_tss_widget_max_respects_draft_and_session_values():
    assert _resolve_near_term_tss_widget_max(60, 110, 95) == 180
    assert _resolve_near_term_tss_widget_max(40, 185, 120) == 185
    assert _resolve_near_term_tss_widget_max(55, 80, 210) == 210


def test_normalize_planning_workspace_mode_falls_back_without_goal_plan():
    assert _normalize_planning_workspace_mode("Собрать план", has_goal_plan=False) == "Собрать план"
    assert _normalize_planning_workspace_mode("Скорректировать выполнение", has_goal_plan=False) == "Собрать план"
    assert _normalize_planning_workspace_mode("Экспорт и детали", has_goal_plan=False) == "Собрать план"
    assert _normalize_planning_workspace_mode("Экспорт и детали", has_goal_plan=True) == "Экспорт и детали"


def test_resolve_planning_start_week_shifts_late_week_build_to_next_monday():
    assert _resolve_planning_start_week(date(2026, 6, 20)) == date(2026, 6, 22)
    assert _resolve_planning_start_week(date(2026, 6, 19)) == date(2026, 6, 22)
    assert _resolve_planning_start_week(date(2026, 6, 18)) == date(2026, 6, 15)


def test_resolve_plan_fact_calendar_default_week_prefers_current_plan_week():
    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        [220, 240, 180],
        ["Base", "Build", "Taper"],
        "Олимпийка",
        date(2026, 6, 15),
        goal_type="Триатлон",
        load_state="balanced",
    )
    goal_plan = {
        "daily_plan": daily_plan,
        "weekly_summary": weekly_summary,
    }

    assert _resolve_plan_fact_calendar_default_week(goal_plan, reference_date=date(2026, 6, 15)) == 0
    assert _resolve_plan_fact_calendar_default_week(goal_plan, reference_date=date(2026, 6, 23)) == 1
    assert _resolve_plan_fact_calendar_default_week(goal_plan, reference_date=date(2026, 6, 30)) == 2


def test_build_plan_fact_calendar_rows_merge_plan_and_same_day_activity():
    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        [220, 240],
        ["Base", "Build"],
        "Олимпийка",
        date(2026, 6, 15),
        goal_type="Триатлон",
        load_state="balanced",
    )
    session_templates = build_daily_session_templates(
        daily_plan,
        weekly_summary,
        goal_type="Триатлон",
        distance="Олимпийка",
    )
    goal_plan = {
        "daily_plan": daily_plan,
        "weekly_summary": weekly_summary,
        "session_templates": session_templates,
    }
    target_idx = next(
        index
        for index, template in enumerate(session_templates[:7])
        if str(template.get("sport") or "") == "bike"
    )
    target_date = session_templates[target_idx]["date"]
    activities_df = pd.DataFrame(
        [
            {
                "date": target_date,
                "sport": "cycling",
                "duration_minutes": 95,
                "tss": 86,
            }
        ]
    )

    rows = _build_plan_fact_calendar_rows(
        goal_plan,
        activities_df,
        week_index=0,
        reference_date=date(2026, 6, 20),
    )

    matched_row = next(row for row in rows if row["date"] == target_date)
    assert matched_row["status"] == "matched"
    assert matched_row["date_label"] == "Пн 15.06"
    assert matched_row["focus_action_label"] == "Подтвердить Garmin"
    assert matched_row["actual_sport_label"] == "вело"
    assert matched_row["actual_activity_count"] == 1
    assert matched_row["actual_total_tss"] == 86.0


def test_build_plan_fact_calendar_rows_marks_other_sport_and_upcoming_days():
    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        [220, 240],
        ["Base", "Build"],
        "Олимпийка",
        date(2026, 6, 15),
        goal_type="Триатлон",
        load_state="balanced",
    )
    session_templates = build_daily_session_templates(
        daily_plan,
        weekly_summary,
        goal_type="Триатлон",
        distance="Олимпийка",
    )
    goal_plan = {
        "daily_plan": daily_plan,
        "weekly_summary": weekly_summary,
        "session_templates": session_templates,
    }
    run_template = next(
        template
        for template in session_templates[:7]
        if str(template.get("sport") or "") == "run"
    )
    activities_df = pd.DataFrame(
        [
            {
                "date": run_template["date"],
                "sport": "swimming",
                "duration_minutes": 48,
                "tss": 39,
            }
        ]
    )

    rows = _build_plan_fact_calendar_rows(
        goal_plan,
        activities_df,
        week_index=0,
        reference_date=date(2026, 6, 18),
    )

    mismatch_row = next(row for row in rows if row["date"] == run_template["date"])
    upcoming_row = next(row for row in rows if row["date"] == "2026-06-20")
    assert mismatch_row["status"] == "other_sport"
    assert mismatch_row["date_label"] == "Чт 18.06"
    assert mismatch_row["focus_action_label"] == "Проверить mismatch"
    assert mismatch_row["actual_sport_label"] == "плавание"
    assert upcoming_row["status"] == "upcoming"
    assert upcoming_row["focus_action_label"] == "Открыть день"


def test_build_plan_fact_focus_action_matches_status_intent():
    assert _build_plan_fact_focus_action("matched") == {
        "label": "Подтвердить Garmin",
        "hint": "У дня уже найден совпавший факт: подтвердите автоподстановку или поправьте его перед checkpoint.",
    }
    assert _build_plan_fact_focus_action("planned_only")["label"] == "Зафиксировать факт"
    assert _build_plan_fact_focus_action("other_sport")["label"] == "Проверить mismatch"
    assert _build_plan_fact_focus_action("unplanned_actual")["label"] == "Проверить вне плана"
    assert _build_plan_fact_focus_action("upcoming")["label"] == "Открыть день"
    assert _build_plan_fact_focus_action("off_day")["label"] == "Проверить отдых"


def test_build_plan_fact_calendar_markup_is_compact_html():
    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        [220, 240],
        ["Base", "Build"],
        "Олимпийка",
        date(2026, 6, 15),
        goal_type="Триатлон",
        load_state="balanced",
    )
    session_templates = build_daily_session_templates(
        daily_plan,
        weekly_summary,
        goal_type="Триатлон",
        distance="Олимпийка",
    )
    goal_plan = {
        "daily_plan": daily_plan,
        "weekly_summary": weekly_summary,
        "session_templates": session_templates,
    }
    rows = _build_plan_fact_calendar_rows(
        goal_plan,
        activities_df=None,
        week_index=0,
        reference_date=date(2026, 6, 20),
    )

    markup = _build_plan_fact_calendar_markup(rows)

    assert markup.startswith("<div class='pfv-grid'><div class='pfv-card'")
    assert markup.count("class='pfv-card'") == 7
    assert "</div><div class='pfv-card'" in markup
    assert "\n" not in markup


def test_build_plan_fact_week_summary_counts_signal_states():
    summary = _build_plan_fact_week_summary(
        [
            {"status": "matched"},
            {"status": "matched"},
            {"status": "other_sport"},
            {"status": "planned_only"},
            {"status": "unplanned_actual"},
            {"status": "upcoming"},
            {"status": "off_day"},
        ]
    )

    assert summary == {
        "matched": 2,
        "mismatch": 2,
        "prefill_ready": 2,
        "unplanned_actual": 1,
        "upcoming": 1,
    }


def test_build_daily_session_rows_uses_week_structure_metadata():
    rows = _build_daily_session_rows(
        {
            "daily_plan": [
                (datetime(2026, 6, 15), 0.0, {"run": 0.0, "bike": 0.0, "swim": 0.0}),
                (datetime(2026, 6, 16), 55.0, {"run": 55.0, "bike": 0.0, "swim": 0.0}),
            ],
            "weekly_summary": [
                {
                    "day_roles": ["off", "quality", "easy", "easy", "recovery", "long", "easy"],
                    "day_focuses": [
                        "Отдых",
                        "Качество • бег",
                        "Легкая • бег",
                        "Легкая • бег",
                        "Восстановление • бег",
                        "Длительная • бег",
                        "Легкая • бег",
                    ],
                }
            ],
        }
    )

    assert rows[0]["session_role"] == "off"
    assert rows[1]["session_role"] == "quality"
    assert rows[1]["session_focus"] == "Качество • бег"


def test_build_daily_session_rows_prefers_session_templates_when_present():
    rows = _build_daily_session_rows(
        {
            "daily_plan": [
                (datetime(2026, 6, 15), 55.0, {"run": 0.0, "bike": 55.0, "swim": 0.0}),
            ],
            "weekly_summary": [
                {
                    "phase": "Build",
                    "day_roles": ["quality", "easy", "easy", "easy", "recovery", "long", "off"],
                    "day_focuses": ["Качество • бег", "—", "—", "—", "—", "—", "—"],
                }
            ],
            "session_templates": [
                {
                    "phase": "Build",
                    "sport": "bike",
                    "session_role": "quality",
                    "session_focus": "Качество • вело",
                    "export_name": "Триатлон Олимпийка — Качество • вело",
                    "duration_minutes": 90,
                }
            ],
        }
    )

    assert rows[0]["phase"] == "Build"
    assert rows[0]["sport"] == "bike"
    assert rows[0]["session_focus"] == "Качество • вело"
    assert rows[0]["session_name"] == "Триатлон Олимпийка — Качество • вело"
    assert rows[0]["duration_minutes"] == 90


def test_build_near_term_draft_preview_summarizes_weekly_effect_before_apply():
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
    goal_plan = {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "weeks_to_race": len(weekly_tss_plan),
        "start_week": date(2026, 6, 8),
        "weekly_tss_plan": weekly_tss_plan,
        "base_weekly_tss_plan": [220, 240, 180],
        "phases": phases,
        "daily_plan": daily_plan,
        "session_templates": build_daily_session_templates(
            daily_plan,
            weekly_summary,
            goal_type="Триатлон",
            distance="Олимпийка",
        ),
        "weekly_summary": weekly_summary,
        "constraint_summary": {"notes": ["Базовый план под текущую доступность."]},
    }
    edit_rows = build_near_term_edit_rows(goal_plan, horizon_days=7)
    current_row = edit_rows[1]
    draft_rows = build_near_term_edit_draft_rows(
        edit_rows,
        goal_type=goal_plan["goal_type"],
        distance=goal_plan["distance"],
        overrides_by_index={
            int(current_row["index"]): {
                "session_role": current_row["current_role"],
                "sport": current_row["current_sport"],
                "total_tss": current_row["current_total_tss"] + 15,
            }
        },
    )
    draft_goal_plan = apply_near_term_day_edits(goal_plan, draft_rows, horizon_days=7)

    preview = _build_near_term_draft_preview(goal_plan, draft_goal_plan)

    assert preview["changed_week_count"] == 1
    assert preview["near_term_edit"] is not None
    assert preview["near_term_edit"]["edited_day_count"] == 1
    assert preview["near_term_edit"]["total_delta_tss"] == 15
    assert preview["near_term_edit"]["post_edit_strategy"] == "keep"
    assert preview["near_term_edit"]["risk_level"] in {"low", "medium", "high"}
    assert preview["weekly_rows"][0]["Неделя"].startswith("1 • 08.06")
    assert preview["weekly_rows"][0]["Δ TSS"] == "+15"
    assert "ручная правка: 1 дн." in preview["weekly_rows"][0]["Почему"]


def test_build_near_term_draft_preview_carries_follow_up_strategy_into_future_weeks():
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
    goal_plan = {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "weeks_to_race": len(weekly_tss_plan),
        "start_week": date(2026, 6, 8),
        "weekly_tss_plan": weekly_tss_plan,
        "base_weekly_tss_plan": [220, 240, 180],
        "phases": phases,
        "daily_plan": daily_plan,
        "session_templates": build_daily_session_templates(
            daily_plan,
            weekly_summary,
            goal_type="Триатлон",
            distance="Олимпийка",
        ),
        "weekly_summary": weekly_summary,
        "constraint_summary": {
            "catch_up_strategy": "catch_up",
            "current_tsb": -4.0,
            "load_state": "balanced",
            "notes": ["Базовый план под текущую доступность."],
        },
    }
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
    draft_goal_plan = apply_near_term_day_edits(
        goal_plan,
        draft_rows,
        horizon_days=7,
        post_edit_strategy="catch_up",
    )

    preview = _build_near_term_draft_preview(goal_plan, draft_goal_plan)

    assert preview["changed_week_count"] >= 2
    assert preview["near_term_edit"] is not None
    assert preview["near_term_edit"]["post_edit_strategy"] == "catch_up"
    assert preview["near_term_edit"]["future_delta_tss"] > 0
    assert preview["near_term_edit"]["risk_badge"] == "Риск низкий"
    assert "Наверстать аккуратно" in preview["near_term_edit"]["follow_up_description"]
    assert any("ручной возврат" in row["Почему"] for row in preview["weekly_rows"])


def test_build_goal_plan_transition_preview_can_describe_rollback_to_previous_version():
    current_goal_plan = {
        "weekly_summary": [
            {"week_start": date(2026, 6, 8), "weekly_tss": 260, "adjustment_note": "ручная правка: 2 дн., Δ +40 TSS"},
            {"week_start": date(2026, 6, 15), "weekly_tss": 220, "adjustment_note": "ручная разгрузка -15 TSS"},
        ],
        "constraint_summary": {
            "near_term_edit": {
                "is_active": True,
                "edited_day_count": 2,
                "horizon_days": 7,
                "total_delta_tss": 40,
                "label": "Ручная правка ближнего горизонта",
                "post_edit_strategy": "keep",
                "future_target_tss": -15,
                "future_delta_tss": -15,
                "future_weeks": 2,
                "future_week_count": 1,
            }
        },
    }
    previous_goal_plan = {
        "weekly_summary": [
            {"week_start": date(2026, 6, 8), "weekly_tss": 220, "adjustment_note": "—"},
            {"week_start": date(2026, 6, 15), "weekly_tss": 240, "adjustment_note": "—"},
        ],
        "constraint_summary": {},
    }

    preview = _build_goal_plan_transition_preview(current_goal_plan, previous_goal_plan)

    assert preview["changed_week_count"] == 2
    assert preview["near_term_edit"] is None
    assert preview["weekly_rows"][0]["Δ TSS"] == "-40"
    assert preview["weekly_rows"][1]["Станет TSS"] == 240


def test_build_plan_explainability_carries_manual_edit_risk_signal():
    explain = _build_plan_explainability(
        {
            "weekly_tss_plan": [220, 215, 180],
            "base_weekly_tss_plan": [220, 240, 180],
            "phases": ["Base", "Build", "Taper"],
            "weekly_summary": [
                {"week_start": date(2026, 6, 8), "adjustment_note": "ручная правка: 2 дн., Δ +40 TSS"},
                {"week_start": date(2026, 6, 15), "adjustment_note": "ручная разгрузка -15 TSS"},
                {"week_start": date(2026, 6, 22), "adjustment_note": "—"},
            ],
            "constraint_summary": {
                "notes": ["Базовый план под текущую доступность."],
                "near_term_edit": {
                    "is_active": True,
                    "edited_day_count": 2,
                    "horizon_days": 7,
                    "total_delta_tss": 40,
                    "label": "Ручная правка ближнего горизонта",
                    "post_edit_strategy": "keep",
                    "future_target_tss": 0,
                    "future_delta_tss": 0,
                    "future_weeks": 2,
                    "future_week_count": 0,
                    "origin_kind": "execution_microcycle_override",
                    "origin_checkpoint_id": 44,
                    "origin_checkpoint_source": "execution_feedback",
                    "origin_plan_adjustment_label": "Нагрузка урезана",
                    "origin_weekly_review_headline": "Пропущена ключевая сессия",
                    "origin_microcycle_headline": "Ближайшие 2-3 дня: вернуть структуру без второй quality-сессии",
                    "risk_level": "high",
                    "risk_focus": "overload",
                    "risk_reasons": [
                        "в ближайшие 7 дн. добавлено +40 TSS",
                        "убран день полного отдыха",
                    ],
                    "risk_guardrail": "Верните часть TSS или оставьте один явный лёгкий день.",
                },
            },
        }
    )

    assert explain["near_term_edit"] is not None
    assert explain["near_term_edit"]["risk_level"] == "high"
    assert explain["near_term_edit"]["risk_badge"] == "Высокий риск перегруза"
    assert explain["near_term_edit"]["origin_checkpoint_id"] == 44
    assert "execution microcycle" in explain["near_term_edit"]["origin_label"].lower()
    assert "лёгкий день" in explain["near_term_edit"]["risk_guardrail"]

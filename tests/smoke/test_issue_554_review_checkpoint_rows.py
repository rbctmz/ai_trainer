"""Issue #554 review gate: a daily row without projected leaf sessions keeps its load.

Проверяется цепочка `restore_goal_plan_from_checkpoint → build_weekly_rebalance_preview
→ apply_weekly_rebalance_preview`, то есть именно тот сценарий, который нашёл
независимым ревьюером: частичный исторический checkpoint (валидные дневные строки
40/30 TSS, но только один legacy-шаблон сессии). Второй шаблон достраивается до `sessions=[]`,
и до правки `project_daily_plan_from_session_templates` создавал нулевую карту
дисциплин ещё до того, как хоть одна сессия внесла нагрузку: строка дня, к которой
rebalance не обращался, обнулялась.

Инвариант: день, у которого в шаблоне нет ни одной спроецированной листовой сессии,
обязан остаться ровно таким, каким был; карта дисциплин, заполненная нулями,
строится только после реального вклада хотя бы одной сессии.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime

import pytest

from models.plan_actual_reconciliation import (
    apply_weekly_rebalance_preview,
    build_weekly_rebalance_preview,
)
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from models.training_planner import project_daily_plan_from_session_templates

pytestmark = pytest.mark.smoke

START = date(2026, 7, 6)
AS_OF = date(2026, 7, 5)
# Валидные исторические строки: 40 TSS в первый день, 30 TSS во второй.
DAY_ONE_TSS = 40.0
DAY_TWO_TSS = 30.0


def _partial_checkpoint() -> dict:
    """Двухдневный исторический checkpoint с одним legacy-шаблоном сессии."""
    return {
        "id": 554,
        "goal_plan_snapshot": {
            "goal_type": "Вело",
            "distance": "—",
            "start_week": "2026-07-06",
            "phases": ["Base", "Build"],
            "weekly_tss_plan": [70],
            "weekly_summary": [
                {
                    "week_start": "2026-07-06",
                    "phase": "Build",
                    "weekly_tss": 70,
                    "bike": 70.0,
                    "run": 0.0,
                    "swim": 0.0,
                    "day_roles": ["easy", "easy"] + ["off"] * 5,
                    "day_focuses": ["Аэробная • вело", "Аэробная • вело"] + ["Отдых"] * 5,
                    "adjustment_note": "—",
                }
            ],
            "daily_plan": [
                {"date": "2026-07-06", "total_tss": DAY_ONE_TSS, "parts": {"bike": DAY_ONE_TSS}},
                {"date": "2026-07-07", "total_tss": DAY_TWO_TSS, "parts": {"bike": DAY_TWO_TSS}},
            ],
            # Legacy-шаблон без ключа `sessions`: только первый день.
            "session_templates": [
                {
                    "date": "2026-07-06",
                    "week_index": 0,
                    "day_index": 0,
                    "phase": "Build",
                    "session_role": "easy",
                    "session_focus": "Аэробная • вело",
                    "sport": "bike",
                    "sport_label": "Вело",
                    "duration_minutes": 60,
                    "template_key": "build:easy:bike",
                    "export_name": "Easy ride",
                    "description": "Total TSS: 40\nBike: 40",
                }
            ],
            "constraint_summary": {},
        },
    }


def _sufficient_reconciliation(*, actual_tss: float) -> dict:
    """Reconciliation с достаточным качеством данных и перегрузом над планом."""
    return {
        "rule_version": "rebalance-1",
        "base_checkpoint_id": 554,
        "data_quality": {
            "planned_session_count": 5,
            "matched_count": 4,
            "ambiguous_count": 0,
            "coverage": 0.8,
            "status": "sufficient",
            "reasons": [],
        },
        "metrics": {
            "planned_tss": 100.0,
            "matched_actual_tss": actual_tss,
            "unplanned_tss": 0.0,
            "total_actual_tss": actual_tss,
        },
        "rows": [],
        "unplanned_activities": [],
    }


def _restored() -> dict:
    restored = restore_goal_plan_from_checkpoint(_partial_checkpoint())
    assert isinstance(restored, dict)
    return restored


def test_partial_checkpoint_restores_padded_template_without_leaf_sessions() -> None:
    """Восстановление достраивает второй шаблон до `sessions=[]`, не теряя строки."""
    restored = _restored()

    assert [row[1] for row in restored["daily_plan"]] == [DAY_ONE_TSS, DAY_TWO_TSS]
    assert [row[2] for row in restored["daily_plan"]] == [
        {"bike": DAY_ONE_TSS},
        {"bike": DAY_TWO_TSS},
    ]

    templates = restored["session_templates"]
    assert len(templates) == 2
    first_session = templates[0]["sessions"][0]
    assert first_session["sport"] == "bike"
    assert first_session["total_tss"] == pytest.approx(DAY_ONE_TSS, abs=0.01)
    # Достроенный второй шаблон не несёт исполняемой сессии.
    assert templates[1]["sessions"] == []


def test_projection_keeps_original_row_when_template_has_no_leaf_sessions() -> None:
    """День без спроецированных листовых сессий сохраняет исходную строку дословно."""
    day_one = (datetime(2026, 7, 6), DAY_ONE_TSS, {"bike": DAY_ONE_TSS})
    day_two = (datetime(2026, 7, 7), DAY_TWO_TSS, {"bike": DAY_TWO_TSS})
    templates = [
        {
            "session_role": "easy",
            "sessions": [{"kind": "single", "sport": "bike", "total_tss": DAY_ONE_TSS}],
        },
        # Ни листовых сессий, ни роли: ровно то, что даёт достроенный шаблон.
        {"sessions": []},
    ]

    projected = project_daily_plan_from_session_templates([day_one, day_two], templates)

    assert projected[0][1] == pytest.approx(DAY_ONE_TSS, abs=0.01)
    assert projected[0][2] == {"bike": DAY_ONE_TSS}
    # День без вклада сессий остаётся прежним, а не обнуляется.
    assert projected[1][1] == pytest.approx(DAY_TWO_TSS, abs=0.01)
    assert projected[1][2] == {"bike": DAY_TWO_TSS}
    assert projected[1] == day_two


def test_projection_builds_zero_filled_discipline_map_only_after_contribution() -> None:
    """Нулевая карта дисциплин появляется только после вклада хотя бы одной сессии."""
    day = (datetime(2026, 7, 6), DAY_ONE_TSS, {"bike": DAY_ONE_TSS, "run": 8.0})

    untouched = project_daily_plan_from_session_templates([day], [{"sessions": []}])
    assert untouched[0] == day

    contributed = project_daily_plan_from_session_templates(
        [day],
        [
            {
                "session_role": "easy",
                "sessions": [{"kind": "single", "sport": "bike", "total_tss": 30.0}],
            }
        ],
    )
    # После вклада карта дисциплин строится явно, включая нулевую дисциплину строки.
    assert contributed[0][1] == pytest.approx(30.0, abs=0.01)
    assert contributed[0][2] == {"bike": 30.0, "run": 0.0}


def test_rebalance_addressing_first_day_leaves_untouched_day_byte_identical() -> None:
    """Reindex 0 не имеет права менять нетронутый второй день частичного checkpoint."""
    restored = _restored()
    before = deepcopy(restored["daily_plan"])
    assert [row[1] for row in before] == [DAY_ONE_TSS, DAY_TWO_TSS]

    preview = build_weekly_rebalance_preview(
        restored,
        _sufficient_reconciliation(actual_tss=110.0),
        as_of=AS_OF,
    )

    assert preview["status"] == "proposal"
    assert preview["reason"] == "over_plan_future_reduction"
    assert [change["index"] for change in preview["changes"]] == [0]

    updated = apply_weekly_rebalance_preview(restored, preview)
    after = updated["daily_plan"]

    # Обработанный день сдвигается предсказуемо: 40 → 35.
    assert after[0][1] == pytest.approx(35.0, abs=0.01)
    assert after[0][2] == {"bike": 35.0}
    # Нетронутый день сохраняется байт-в-байт: было 30 TSS, осталось 30 TSS.
    assert after[1] == before[1]
    assert after[1][1] == pytest.approx(DAY_TWO_TSS, abs=0.01)
    assert after[1][2] == {"bike": DAY_TWO_TSS}
    assert [row[1] for row in after] == [35.0, DAY_TWO_TSS]

"""Issue #554 review gate: rebalance descriptions follow the effective load.

Проверяется цепочка `build_daily_session_templates → ensure_session_identities →
build_weekly_rebalance_preview → apply_weekly_rebalance_preview` на
материализованных по мощности велосессиях, то есть именно тот сценарий, который
нашёл независимый ревьюер: запрошенный бюджет дня уменьшается, но прескрипция по
NP несёт другую эффективную нагрузку (качество: 60 TSS запрошено → 59.8 TSS по NP). Числа обновлены после правки находки 556: rescale теперь считает от эффективной нагрузки, поэтому одобренная цель 60 TSS и доставляется как 59.8, а не как прежние 48.8 (прежнее значение недоставляло одобренный объём — это и есть дефект, на который указало ревью).
До правки `apply_weekly_rebalance_preview` пересобирал описание из запрошенного
бюджета, поэтому план и календарь держали `Total TSS: 60.0` / `Bike: 60.0`, тогда
как скаляр сессии, строка дневного плана, недельная сводка и доставка несли 59.8.

Инвариант: описание сессии и дня строится из той же эффективной нагрузки, что
несут скаляр сессии, строка дневного плана и недельная сводка; запрошенный бюджет
планирования остаётся виден только в `parameter_snapshot.requested_tss`/`changes`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from models.plan_actual_reconciliation import (
    apply_weekly_rebalance_preview,
    build_weekly_rebalance_preview,
)
from models.session_identity import ensure_session_identities
from models.training_planner import build_daily_session_templates


pytestmark = pytest.mark.smoke

START = datetime(2026, 7, 13)
AS_OF = date(2026, 7, 12)
ZONES = {"ftp": 200}


def _description_value(description: str, prefix: str) -> str:
    """Значение строки описания по префиксу — ровно так, как его видит пользователь."""
    for line in str(description or "").splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    raise AssertionError(f"нет строки {prefix!r} в описании:\n{description}")


def _plan(*, day_tss: float, parts: dict[str, float], role: str, focus: str, brick: bool = False) -> dict:
    """Неделя с одной целевой сессией в первый день и офф-днями вокруг."""
    daily = [
        (
            START + timedelta(days=index),
            day_tss if index == 0 else 0.0,
            {key: (value if index == 0 else 0.0) for key, value in parts.items()},
        )
        for index in range(7)
    ]
    summary = [
        {
            "phase": "Build",
            "weekly_tss": int(round(day_tss)),
            "day_roles": [role] + ["off"] * 6,
            "day_focuses": [focus] + ["Отдых"] * 6,
        }
    ]
    templates = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        zone_snapshot=ZONES,
        brick_day_indices={0} if brick else (),
    )
    return ensure_session_identities(
        {
            "goal_type": "Триатлон",
            "distance": "Олимпийка",
            "daily_plan": daily,
            "session_templates": templates,
            "weekly_summary": summary,
            "weekly_tss_plan": [int(round(day_tss))],
            "constraint_summary": {},
        }
    )


def _quality_bike_plan() -> dict:
    """Качественная велосессия: 80 TSS запрошено, 65.2 TSS по NP."""
    return _plan(
        day_tss=80.0,
        parts={"run": 0.0, "bike": 80.0, "swim": 0.0},
        role="quality",
        focus="Качество",
    )


def _sufficient_reconciliation(*, actual_tss: float) -> dict:
    """Reconciliation с достаточным качеством данных и перегрузом над планом."""
    return {
        "rule_version": "plan_actual_match_v2",
        "base_checkpoint_id": 63,
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


def _hand_built_proposal(*, before_tss: float, after_tss: float) -> dict:
    """Предложение ровно того вида, каким его отдаёт preview (редукция первого дня)."""
    return {
        "status": "proposal",
        "rule_version": "weekly_rebalance_v1",
        "as_of": AS_OF.isoformat(),
        "base_checkpoint_id": 63,
        "preview_fingerprint": "issue-554-review",
        "future_tss_delta": round(after_tss - before_tss, 1),
        "changes": [
            {"index": 0, "before_tss": before_tss, "after_tss": after_tss},
        ],
        "reconciliation_snapshot": {},
    }


def test_quality_bike_description_follows_effective_np_load_after_rebalance() -> None:
    """60 TSS запрошено, 59.8 TSS по NP: описание обязано нести 59.8, а не бюджет."""
    plan = _quality_bike_plan()
    before_session = plan["session_templates"][0]["sessions"][0]
    assert before_session["parameter_snapshot"]["requested_tss"] == 80.0
    assert before_session["parameter_snapshot"]["target_tss"] == 65.2
    # Материализация уже пишет в описание эффективную нагрузку — rebalance обязан её сохранить.
    assert _description_value(before_session["description"], "Total TSS:") == "65.2"

    updated = apply_weekly_rebalance_preview(
        plan,
        _hand_built_proposal(before_tss=80.0, after_tss=60.0),
    )

    template = updated["session_templates"][0]
    session = template["sessions"][0]
    day = updated["daily_plan"][0]
    week = updated["weekly_summary"][0]

    # Запрошенный бюджет планирования остаётся виден только в снимке параметров.
    assert session["parameter_snapshot"]["requested_tss"] == 60.0
    assert session["parameter_snapshot"]["target_tss"] == 59.8
    assert session["total_tss"] == 59.8
    assert day[1] == 59.8
    assert day[2] == {"bike": 59.8, "run": 0.0, "swim": 0.0}
    assert week["bike"] == 59.8
    # Недельная сводка держит целое поле: 59.8 округляется до 60.
    assert week["weekly_tss"] == 60

    for description in (session["description"], template["description"]):
        assert _description_value(description, "Total TSS:") == "59.8"
        assert _description_value(description, "Bike:") == "59.8"
        assert _description_value(description, "Run:") == "0.0"
        assert _description_value(description, "Оценка длительности:") == "55 мин"
        # Запрошенный бюджет не имеет права просачиваться в план и календарь.
        assert "Total TSS: 60.0" not in description
        assert "Bike: 60.0" not in description


def test_easy_bike_description_matches_day_row_and_weekly_summary_after_real_preview() -> None:
    """Реальный preview: 80 → 70 TSS запрошено, 69.7 TSS по NP на всех поверхностях."""
    plan = _plan(
        day_tss=80.0,
        parts={"run": 0.0, "bike": 80.0, "swim": 0.0},
        role="easy",
        focus="Аэробная • вело",
    )
    preview = build_weekly_rebalance_preview(
        plan,
        _sufficient_reconciliation(actual_tss=180.0),
        as_of=AS_OF,
    )

    assert preview["status"] == "proposal"
    assert preview["reduction_budget_tss"] == 10
    assert [change["after_tss"] for change in preview["changes"]] == [70.0]

    updated = apply_weekly_rebalance_preview(plan, preview)

    template = updated["session_templates"][0]
    session = template["sessions"][0]
    day = updated["daily_plan"][0]
    week = updated["weekly_summary"][0]

    assert session["parameter_snapshot"]["requested_tss"] == 70.0
    assert session["parameter_snapshot"]["target_tss"] == 69.7
    assert session["total_tss"] == 69.7
    assert day[1] == 69.7
    assert day[2] == {"bike": 69.7, "run": 0.0, "swim": 0.0}
    assert week["bike"] == 69.7
    assert week["weekly_tss"] == 70

    for description in (session["description"], template["description"]):
        assert _description_value(description, "Total TSS:") == "69.7"
        assert _description_value(description, "Bike:") == "69.7"
        assert _description_value(description, "Оценка длительности:") == "99 мин"
        assert "Total TSS: 70.0" not in description


def test_brick_description_follows_projected_legs_after_real_preview() -> None:
    """Кирпич: описание дня берёт спроецированные ноги (70.4 = 52.9 + 17.5)."""
    plan = _plan(
        day_tss=80.0,
        parts={"run": 20.0, "bike": 60.0, "swim": 0.0},
        role="easy",
        focus="Кирпич",
        brick=True,
    )
    before_session = plan["session_templates"][0]["sessions"][0]
    assert before_session["kind"] == "composite"
    assert [leg["sport"] for leg in before_session["legs"]] == ["bike", "run"]

    preview = build_weekly_rebalance_preview(
        plan,
        _sufficient_reconciliation(actual_tss=180.0),
        as_of=AS_OF,
    )
    assert preview["status"] == "proposal"
    assert [change["after_tss"] for change in preview["changes"]] == [70.0]

    updated = apply_weekly_rebalance_preview(plan, preview)

    template = updated["session_templates"][0]
    session = template["sessions"][0]
    day = updated["daily_plan"][0]
    week = updated["weekly_summary"][0]

    # Запрошенные ноги: вело 52.5, бег 17.5; эффективное вело по NP — 52.9.
    assert [leg["parameter_snapshot"].get("requested_tss") for leg in session["legs"]] == [52.5, None]
    assert [leg["target_tss"] for leg in session["legs"]] == [52.9, 17.5]
    assert session["parameter_snapshot"]["requested_tss"] == 70.0
    assert session["parameter_snapshot"]["target_tss"] == 70.4
    assert session["total_tss"] == 70.4
    assert day[1] == 70.4
    assert day[2] == {"bike": 52.9, "run": 17.5, "swim": 0.0}
    assert week["bike"] == 52.9
    assert week["run"] == 17.5
    assert week["weekly_tss"] == 70

    for description in (session["description"], template["description"]):
        assert _description_value(description, "Total TSS:") == "70.4"
        assert _description_value(description, "Bike:") == "52.9"
        assert _description_value(description, "Run:") == "17.5"
        assert "Bike: 52.5" not in description

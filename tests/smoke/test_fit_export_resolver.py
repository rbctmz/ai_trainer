"""Issue #317: UI FIT/TCX-экспорт должен honour'ить материализованные цели.

Резолвер шагов для day-template — общий для UI-экспорта; зеркалирует
api.planning_service.export_workout: материализованные шаги (single leaf или
конкатенация ног composite) используются, когда они есть, а легаси-fallback
build_steps_for_sport включается только при их отсутствии (договор #299).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from models.fit_export import generate_fit_csv, resolve_export_steps
from models.session_identity import ensure_session_identities
from models.training_planner import build_daily_session_templates


pytestmark = pytest.mark.smoke


def _single_day_template(*, sport_tss: dict[str, float], zone_snapshot: dict[str, float], day_role: str = "quality"):
    """Построить one-day day-template через канонический планировщик (Builder A)."""
    dt = datetime(2026, 7, 13)
    daily = [(dt, sum(sport_tss.values()), {**{"run": 0.0, "bike": 0.0, "swim": 0.0}, **sport_tss})]
    summary = [{"phase": "Build", "day_roles": [day_role], "day_focuses": ["Качество"]}]
    template = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        zone_snapshot=zone_snapshot,
    )[0]
    plan = ensure_session_identities(
        {"goal_type": "Триатлон", "daily_plan": daily, "session_templates": [template]}
    )
    return plan["session_templates"][0]


def _brick_day_template(zone_snapshot: dict[str, float]):
    """Построить composite/brick day-template (Builder B)."""
    dt = datetime(2026, 7, 18)
    daily = [(dt, 80.0, {"run": 25.0, "bike": 55.0, "swim": 0.0})]
    summary = [{"phase": "Build", "day_roles": ["long"], "day_focuses": ["Длительная"]}]
    template = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        zone_snapshot=zone_snapshot,
        brick_day_indices={0},
    )[0]
    plan = ensure_session_identities(
        {"goal_type": "Триатлон", "daily_plan": daily, "session_templates": [template]}
    )
    return plan["session_templates"][0]


def test_resolve_export_steps_single_run_uses_pace_targets():
    template = _single_day_template(
        sport_tss={"run": 40.0},
        zone_snapshot={"threshold_pace": 340.0, "lthr": 165.0},
        day_role="quality",
    )

    sport, steps = resolve_export_steps(
        template,
        total_tss=40.0,
        sport="run",
        session_role="quality",
        phase="Build",
    )

    assert sport == "run"
    assert steps, "expected materialized steps for a run day"
    target_types = {step["target"]["type"] for step in steps}
    assert target_types == {"pace"}, target_types

    fit = generate_fit_csv("Demo Run", sport, steps, created=datetime(2026, 7, 13))
    assert "target_type,0" in fit  # pace (m/s), не пульс
    assert "target_value,2.0,zone" not in fit  # легаси HR-zone маркер отсутствует


def test_resolve_export_steps_bike_uses_power_targets():
    template = _single_day_template(
        sport_tss={"bike": 80.0},
        zone_snapshot={"ftp": 200.0},
        day_role="quality",
    )

    sport, steps = resolve_export_steps(
        template,
        total_tss=80.0,
        sport="bike",
        session_role="quality",
        phase="Build",
    )

    assert sport == "bike"
    assert steps
    target_types = {step["target"]["type"] for step in steps}
    assert target_types == {"power"}, target_types

    fit = generate_fit_csv("Demo Bike", sport, steps, created=datetime(2026, 7, 13))
    assert "target_type,4" in fit  # power (watts)


def test_resolve_export_steps_composite_concatenates_leg_targets():
    template = _brick_day_template(zone_snapshot={"ftp": 200.0, "threshold_pace": 340.0, "lthr": 165.0})

    sport, steps = resolve_export_steps(
        template,
        total_tss=80.0,
        sport="brick",
        session_role="long",
        phase="Build",
    )

    assert steps, "composite day must yield concatenated leg steps"
    target_types = {step["target"]["type"] for step in steps}
    # обе ноги: bike → power, run → pace
    assert target_types == {"power", "pace"}, target_types


def test_resolve_export_steps_legacy_fallback_when_no_materialized_steps():
    # голый template без sessions[] и без materialized_steps — легаси/пустой день
    template = {}

    sport, steps = resolve_export_steps(
        template,
        total_tss=30.0,
        sport="run",
        session_role="easy",
        phase=None,
    )

    # договор #299: легаси-fallback сохранён; таргеты — строковые HR-zone токены
    assert isinstance(steps, list) and steps
    assert all(isinstance(step["target"], str) for step in steps)
    assert any(step["target"].startswith("hr_zone_") for step in steps)

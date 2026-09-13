from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import re

import pytest

from models.planned_bike_tss import (
    apply_bike_tss_rebalance_preview,
    build_bike_tss_rebalance_preview,
    repair_bike_tss_materialization,
)
from models.planning_checkpoints import build_planning_checkpoint
from models.session_identity import ensure_session_identities
from models.training_planner import (
    build_daily_session_templates,
    derive_weekly_sport_buckets_from_sessions,
    project_daily_plan_from_session_templates,
)
from models.workout_catalog import catalog_definitions, materialize_workout, rescale_materialized_session


pytestmark = pytest.mark.smoke


def _definition(key: str):
    return next(item for item in catalog_definitions() if item.template_key == key)


def _session(
    total_tss: float = 36.5,
    *,
    template_key: str = "bike_aerobic_endurance",
    duration_minutes: int = 40,
    session_role: str = "easy",
) -> dict:
    definition = _definition(template_key)
    materialized = materialize_workout(
        definition,
        {"duration_minutes": duration_minutes, "target_tss": total_tss},
        {"ftp": 172},
    )
    return {
        "sport": "bike",
        "sport_label": "вело",
        "session_role": session_role,
        "session_focus": definition.display_name,
        "duration_minutes": duration_minutes,
        "total_tss": total_tss,
        "template_key": definition.template_key,
        "export_name": definition.display_name,
        "description": f"Total TSS: {total_tss}\nОценка длительности: {duration_minutes} мин",
        "materialization_status": materialized["materialization_status"],
        "catalog_version": materialized["catalog_version"],
        "materializer_rule_version": materialized["rule_version"],
        "definition_snapshot": materialized["definition_snapshot"],
        "parameter_snapshot": materialized["parameter_snapshot"],
        "materialized_steps": materialized["steps"],
        "target_provenance": materialized["target_provenance"],
        "structure_status": materialized["structure_status"],
        "structure_evidence": materialized["structure_evidence"],
    }


def _plan() -> dict:
    past = _session()
    future = _session()
    plan = {
        "daily_plan": [
            (datetime(2026, 8, 19), 36.5, {"bike": 36.5}),
            (datetime(2026, 8, 21), 36.5, {"bike": 36.5}),
        ],
        "session_templates": [
            {
                "date": "2026-08-19",
                "phase": "Base",
                "sport": "bike",
                "session_role": "easy",
                "sessions": [past],
            },
            {
                "date": "2026-08-21",
                "phase": "Base",
                "sport": "bike",
                "session_role": "easy",
                "sessions": [future],
            },
        ],
        "weekly_summary": [{"weekly_tss": 73, "bike": 73, "run": 0, "swim": 0}],
        "weekly_tss_plan": [73],
        "constraint_summary": {
            "available_hours": 10.0,
            "available_day_indices": [0, 1, 2, 3, 4, 5, 6],
        },
    }
    return ensure_session_identities(plan)


def test_preview_is_future_only_and_preserves_weekly_budget():
    plan = _plan()
    past_id = plan["session_templates"][0]["sessions"][0]["session_id"]
    future_id = plan["session_templates"][1]["sessions"][0]["session_id"]

    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )

    assert preview["status"] == "proposal"
    assert preview["weekly_budget_preserved"] is True
    assert [item["session_id"] for item in preview["changes"]] == [future_id]
    change = preview["changes"][0]
    assert change["before_tss"] == 36.5
    assert change["honest_tss"] < change["before_tss"]
    assert change["after_duration_minutes"] > change["before_duration_minutes"]
    assert abs(change["after_tss"] - change["before_tss"]) <= 1.0
    assert past_id not in {item["session_id"] for item in preview["changes"]}


def test_apply_changes_only_future_prescription_and_keeps_old_lineage():
    plan = _plan()
    old_past = deepcopy(plan["session_templates"][0]["sessions"][0])
    old_future = deepcopy(plan["session_templates"][1]["sessions"][0])
    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )

    updated = apply_bike_tss_rebalance_preview(plan, preview)
    new_past = updated["session_templates"][0]["sessions"][0]
    new_future = updated["session_templates"][1]["sessions"][0]

    assert new_past == old_past
    assert new_future["duration_minutes"] > old_future["duration_minutes"]
    assert new_future["session_id"] != old_future["session_id"]
    assert new_future["replaces_session_id"] == old_future["session_id"]
    assert new_future["delivery_session_id"] == old_future["session_id"]
    assert sum(
        int(step["duration_seconds"])
        for step in new_future["materialized_steps"]
    ) == new_future["duration_minutes"] * 60
    assert updated["session_templates"][0]["date"] == "2026-08-19"
    assert updated["daily_plan"][0][1] == 36.5
    assert updated["weekly_tss_plan"] == [73]


def test_rebalanced_delivery_uses_old_provider_id_and_new_step_duration():
    from models.intervals_workout_delivery import build_delivery_events

    plan = _plan()
    old_id = plan["session_templates"][1]["sessions"][0]["session_id"]
    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )
    updated = apply_bike_tss_rebalance_preview(plan, preview)

    event = build_delivery_events(updated, ["2026-08-21"])[0]
    assert event["external_id"] == f"ai_trainer:{old_id}"
    assert event["moving_time"] == (
        updated["session_templates"][1]["sessions"][0]["duration_minutes"] * 60
    )

    # Checkpoint #126 was already persisted before the step-copy bug was
    # fixed.  Delivery must repair that stale serialized step list as a
    # compatibility path, without requiring a destructive history rewrite.
    legacy = deepcopy(updated)
    legacy_session = legacy["session_templates"][1]["sessions"][0]
    legacy_session["materialized_steps"] = plan["session_templates"][1]["sessions"][0][
        "materialized_steps"
    ]
    legacy_session.pop("delivery_session_id", None)
    legacy_event = build_delivery_events(legacy, ["2026-08-21"])[0]
    assert legacy_event["external_id"] == f"ai_trainer:{old_id}"
    assert legacy_event["moving_time"] == event["moving_time"]


def test_rebalanced_export_and_delivery_share_persisted_duration_and_identity():
    from api.planning_service import export_workout
    from models.intervals_workout_delivery import build_delivery_events

    plan = _plan()
    old_id = plan["session_templates"][1]["sessions"][0]["session_id"]
    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )
    updated = apply_bike_tss_rebalance_preview(plan, preview)
    session = updated["session_templates"][1]["sessions"][0]
    expected_seconds = [
        int(step["duration_seconds"])
        for step in session["materialized_steps"]
    ]

    tcx = export_workout(
        updated,
        1,
        "tcx",
        session_id=str(session["session_id"]),
    )
    fit = export_workout(
        updated,
        1,
        "fit_csv",
        session_id=str(session["session_id"]),
    )
    events = build_delivery_events(updated, ["2026-08-21"])
    event = next(
        item
        for item in events
        if item["external_id"] == f"ai_trainer:{old_id}"
    )

    assert [
        int(value)
        for value in re.findall(r"<Seconds>(\d+)</Seconds>", tcx["content"])
    ] == expected_seconds
    fit_steps = [
        (int(index), int(seconds), float(target))
        for index, seconds, target in re.findall(
            r"^Data,2,workout_step,message_index,(\d+),,.*?,"
            r"duration_type,0,,duration_time,(\d+),s,"
            r"target_type,4,,target_value,([\d.]+),watts,",
            fit["content"],
            flags=re.MULTILINE,
        )
    ]
    expected_fit_steps = [
        (
            index,
            seconds,
            round(
                (float(step["target"]["low"]) + float(step["target"]["high"]))
                / 2.0,
                1,
            ),
        )
        for index, (step, seconds) in enumerate(
            zip(session["materialized_steps"], expected_seconds)
        )
    ]
    assert fit_steps == expected_fit_steps

    provider_steps = [
        line.strip()
        for line in event["description"].splitlines()[1:]
        if line.strip()
    ]
    expected_provider_steps = []
    for step, seconds in zip(session["materialized_steps"], expected_seconds):
        duration = f"{seconds // 60}m" if seconds % 60 == 0 else f"{seconds}s"
        target = step["target"]
        expected_provider_steps.append(
            f"- {step['name']} {duration} "
            f"{float(target['low']):g}-{float(target['high']):g}w"
        )
    assert provider_steps == expected_provider_steps
    assert "AI Trainer target evidence: power" in tcx["content"]
    assert event["external_id"] == f"ai_trainer:{session['delivery_session_id']}"
    assert event["moving_time"] == sum(expected_seconds)


def test_preview_is_idempotent_when_checkpoint_has_legacy_stale_steps():
    plan = _plan()
    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )
    updated = apply_bike_tss_rebalance_preview(plan, preview)
    session = updated["session_templates"][1]["sessions"][0]
    session["materialized_steps"] = plan["session_templates"][1]["sessions"][0][
        "materialized_steps"
    ]

    repeated = build_bike_tss_rebalance_preview(
        updated,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=8,
    )

    assert repeated["status"] == "no_change"
    assert repeated["reason"] == "no_inconsistent_future_bike_sessions"


def test_materialization_repair_restores_legacy_steps_without_replanning():
    plan = _plan()
    original_past = deepcopy(plan["session_templates"][0]["sessions"][0])
    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )
    updated = apply_bike_tss_rebalance_preview(plan, preview)
    future = updated["session_templates"][1]["sessions"][0]
    future["materialized_steps"] = plan["session_templates"][1]["sessions"][0][
        "materialized_steps"
    ]

    repaired, changed_dates = repair_bike_tss_materialization(
        updated,
        as_of=datetime(2026, 8, 20).date(),
    )

    repaired_future = repaired["session_templates"][1]["sessions"][0]
    assert changed_dates == ["2026-08-21"]
    assert repaired["session_templates"][0]["sessions"][0] == original_past
    assert sum(
        int(step["duration_seconds"])
        for step in repaired_future["materialized_steps"]
    ) == repaired_future["duration_minutes"] * 60
    assert repaired_future["duration_minutes"] == future["duration_minutes"]


def test_preview_ignores_rounding_only_gap_after_repair():
    plan = _plan()
    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )
    updated = apply_bike_tss_rebalance_preview(plan, preview)
    repeated = build_bike_tss_rebalance_preview(
        updated,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=8,
    )

    assert repeated["status"] == "no_change"
    assert repeated["reason"] == "no_inconsistent_future_bike_sessions"


def test_preview_uses_minute_resolution_for_real_power_zone_budget_gaps():
    past = _session()
    progression = _session(
        78.2,
        template_key="bike_aerobic_progression",
        duration_minutes=65,
        session_role="long",
    )
    endurance = _session(38.5, duration_minutes=40)
    plan = ensure_session_identities(
        {
            "daily_plan": [
                (datetime(2026, 8, 19), 36.5, {"bike": 36.5}),
                (datetime(2026, 8, 22), 78.2, {"bike": 78.2}),
                (datetime(2026, 9, 1), 38.5, {"bike": 38.5}),
            ],
            "session_templates": [
                {"date": "2026-08-19", "sessions": [past]},
                {"date": "2026-08-22", "sessions": [progression]},
                {"date": "2026-09-01", "sessions": [endurance]},
            ],
            "weekly_summary": [{"weekly_tss": 153, "bike": 153, "run": 0, "swim": 0}],
            "weekly_tss_plan": [153],
            "constraint_summary": {"available_hours": 10.0},
        }
    )

    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )

    assert preview["status"] == "proposal"
    assert preview["capacity_gaps"] == []
    changes = {item["date"]: item for item in preview["changes"]}
    assert changes["2026-08-22"]["after_duration_minutes"] == 97
    assert changes["2026-09-01"]["after_duration_minutes"] == 55
    assert abs(changes["2026-08-22"]["after_tss"] - 78.2) <= 1.0
    assert abs(changes["2026-09-01"]["after_tss"] - 38.5) <= 1.0


def test_preview_blocks_when_future_duration_exceeds_saved_weekly_budget():
    plan = _plan()
    plan["constraint_summary"]["available_hours"] = 0.75

    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )

    assert preview["status"] == "no_change"
    assert preview["reason"] == "time_budget_gap"
    assert preview["time_budget_preserved"] is False
    assert preview["time_budget_gaps"] == [
        {
            "week_start": "2026-08-17",
            "before_minutes": 80,
                "after_minutes": 92,
            "budget_minutes": 45,
                "delta_minutes": 12,
            "reason": "weekly_duration_over_budget",
        }
    ]


def test_planned_quality_bike_preserves_effective_tss_across_plan_views():
    start = datetime(2026, 8, 17)
    daily = [
        (
            start + timedelta(days=index),
            63.0 if index == 0 else 0.0,
            {"run": 0.0, "bike": 63.0 if index == 0 else 0.0, "swim": 0.0},
        )
        for index in range(7)
    ]
    weekly = [{
        "phase": "Build",
        "day_roles": ["quality"] + ["off"] * 6,
        "day_focuses": ["Качество • вело"] + ["Отдых"] * 6,
        "weekly_tss": 63,
    }]

    templates = build_daily_session_templates(
        daily,
        weekly,
        "Вело",
        "—",
        zone_snapshot={"ftp": 172},
    )
    session = templates[0]["sessions"][0]
    assert session["materialization_status"] == "materialized"
    effective = float(session["parameter_snapshot"]["target_tss"])
    assert session["total_tss"] == pytest.approx(effective, abs=0.01)
    assert sum(step["tss"] for step in session["materialized_steps"]) == pytest.approx(effective, abs=0.01)

    projected_daily = project_daily_plan_from_session_templates(daily, templates)
    assert projected_daily[0][1] == pytest.approx(effective, abs=0.01)
    assert projected_daily[0][2]["bike"] == pytest.approx(effective, abs=0.01)
    projected_weekly = derive_weekly_sport_buckets_from_sessions(weekly, templates)
    assert projected_weekly[0]["bike"] == pytest.approx(effective, abs=0.01)
    assert projected_weekly[0]["weekly_tss"] == int(round(effective))
    assert [int(row["weekly_tss"]) for row in projected_weekly] == [int(round(effective))]


def test_rescaling_lower_effective_tss_does_not_increase_tempo_duration():
    """Понижение эффективной нагрузки не удлиняет сессию.

    Ревизия #554 (находка 556): `rescale_materialized_session` теперь считает от
    эффективной нагрузки материализованной прескрипции, поэтому `target_tss` —
    целевая ЭФФЕКТИВНАЯ нагрузка, а не запрошенный бюджет. Прежняя версия теста
    подавала 60 при запросе 63 и ожидала сокращения: по старой семантике это было
    понижением бюджета, по новой — повышением эффективной цели в полтора раза,
    и удлинение партии корректно (проверяется ниже отдельным утверждением).
    """
    definition = _definition("bike_tempo_sweet_spot")
    materialized = materialize_workout(
        definition,
        {"duration_minutes": 50, "target_tss": 63.0},
        {"ftp": 172},
    )
    session = {
        "sport": "bike",
        "materialization_status": materialized["materialization_status"],
        "duration_minutes": 50,
        "total_tss": materialized["parameter_snapshot"]["target_tss"],
        "parameter_snapshot": materialized["parameter_snapshot"],
        "materialized_steps": materialized["steps"],
        "target_provenance": materialized["target_provenance"],
        "definition_snapshot": materialized["definition_snapshot"],
    }
    # Понижение берётся в пределах полосы шаблона (ниже 36 TSS у этой сессии
    # начинают падать собственные границы шаблона — это отдельный fail-closed).
    scaled = rescale_materialized_session(
        session,
        target_tss=37.0,
        parts={"bike": 37.0},
    )

    assert scaled["materialization_status"] == "materialized"
    assert scaled["duration_minutes"] <= session["duration_minutes"]
    effective = scaled["parameter_snapshot"]["target_tss"]
    assert scaled["total_tss"] == pytest.approx(effective, abs=0.01)
    assert sum(step["tss"] for step in scaled["materialized_steps"]) == pytest.approx(effective, abs=0.01)

    # Обратная сторона контракта: повышение эффективной цели удлиняет предписание,
    # а не маскируется прежним бюджетом.
    raised = rescale_materialized_session(
        session,
        target_tss=60.0,
        parts={"bike": 60.0},
    )
    assert raised["duration_minutes"] > session["duration_minutes"]
    assert raised["parameter_snapshot"]["requested_tss"] == 60.0


def test_preview_fails_closed_when_weekly_duration_budget_is_missing():
    plan = _plan()
    plan["constraint_summary"] = {}

    preview = build_bike_tss_rebalance_preview(
        plan,
        as_of=datetime(2026, 8, 20).date(),
        base_checkpoint_id=7,
    )

    assert preview["status"] == "no_change"
    assert preview["reason"] == "time_budget_data_gap"
    assert preview["time_budget_status"] == "data_gap"
    assert preview["time_budget_preserved"] is False


def test_service_preview_is_read_only_and_confirmation_is_stale_safe(tmp_path):
    from api import planning_service as ps
    from data.database import Database

    db = Database(str(tmp_path / "bike-tss.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_plan()))
    before = db.get_latest_planning_checkpoint()

    preview_result = ps.preview_bike_tss_rebalance(db, as_of="2026-08-20")
    preview = preview_result["preview"]
    assert preview_result["has_plan"] is True
    assert preview["status"] == "proposal"
    assert db.get_latest_planning_checkpoint()["id"] == before["id"]

    confirmed = ps.confirm_bike_tss_rebalance(
        db,
        base_checkpoint_id=before["id"],
        preview_fingerprint=preview["preview_fingerprint"],
        as_of="2026-08-20",
    )
    assert confirmed["checkpoint_source"] == "bike_tss_rebalance"
    assert db.get_latest_planning_checkpoint()["id"] == before["id"] + 1

    with pytest.raises(ps.StalePlanningCheckpointError):
        ps.confirm_bike_tss_rebalance(
            db,
            base_checkpoint_id=before["id"],
            preview_fingerprint=preview["preview_fingerprint"],
            as_of="2026-08-20",
        )

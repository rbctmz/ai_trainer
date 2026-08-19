"""Smoke tests for day recovery after constraint retraction (issue #473, M3)."""
from __future__ import annotations

from copy import deepcopy

import pytest

from data.database import Database
from models.coach_constraints import apply_constraints_to_goal_plan
from models.planning_checkpoints import (
    build_planning_checkpoint,
    restore_goal_plan_from_checkpoint,
    with_checkpoint_provenance,
)


pytestmark = pytest.mark.smoke

TARGET = "2026-08-18"


def _goal_plan() -> dict:
    """Однонедельник: день из двух ног (bike 36.5 + swim 27.5) и два соседних дня."""
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "daily_plan": [
            ("2026-08-17", 30.0, {"run": 30.0}),
            (TARGET, 64.0, {"bike": 36.5, "swim": 27.5}),
            ("2026-08-19", 25.0, {"run": 25.0}),
        ],
        "session_templates": [
            {
                "date": "2026-08-17",
                "session_role": "easy",
                "sport": "run",
                "duration_minutes": 45,
                "sessions": [
                    {
                        "session_id": "atts_run_a",
                        "sport": "run",
                        "total_tss": 30.0,
                        "duration_minutes": 45,
                        "materialization_status": "materialized",
                        "materialized_steps": [],
                    }
                ],
            },
            {
                "date": TARGET,
                "week_index": 0,
                "day_index": 1,
                "phase": "Base",
                "session_role": "easy",
                "sport": "bike",
                "duration_minutes": 40,
                "allocated_parts": {"bike": 36.5, "swim": 27.5},
                "sessions": [
                    {
                        "session_id": "atts_bike_seed",
                        "sport": "bike",
                        "total_tss": 36.5,
                        "duration_minutes": 40,
                        "template_key": "bike_aerobic_endurance",
                        "materialization_status": "materialized",
                        "materialized_steps": [{"name": "steady"}],
                        "definition_snapshot": {"template_key": "bike_aerobic_endurance"},
                    },
                    {
                        "session_id": "atts_swim_seed",
                        "sport": "swim",
                        "total_tss": 27.5,
                        "duration_minutes": 35,
                        "template_key": "swim_endurance",
                        "materialization_status": "materialized",
                        "materialized_steps": [{"name": "easy"}],
                        "definition_snapshot": {"template_key": "swim_endurance"},
                    },
                ],
            },
            {
                "date": "2026-08-19",
                "session_role": "easy",
                "sport": "run",
                "duration_minutes": 40,
                "sessions": [
                    {
                        "session_id": "atts_run_b",
                        "sport": "run",
                        "total_tss": 25.0,
                        "duration_minutes": 40,
                        "materialization_status": "materialized",
                        "materialized_steps": [],
                    }
                ],
            },
        ],
        "weekly_summary": [
            {"week_start": "2026-08-17", "weekly_tss": 119, "bike": 36.5, "swim": 27.5, "run": 55.0}
        ],
        "weekly_tss_plan": [119],
    }


def _collapsed_plan() -> dict:
    """План после whole-day ограничения на целевой день (классический collapse)."""
    constraint = {
        "id": 1,
        "date": TARGET,
        "kind": "unavailable",
        "source": "coach",
        "note": "Плавание отменено пользователем",
        "status": "active",
    }
    updated, _summary = apply_constraints_to_goal_plan(_goal_plan(), [constraint])
    return updated


def _day_template(goal_plan: dict, the_date: str) -> dict:
    templates = list(goal_plan.get("session_templates") or [])
    rows = list(goal_plan.get("daily_plan") or [])
    for index, item in enumerate(rows):
        if isinstance(item, (list, tuple)) and len(item) >= 3 and str(item[0])[:10] == the_date:
            return templates[index]
    for template in templates:
        if isinstance(template, dict) and str(template.get("date"))[:10] == the_date:
            return template
    raise LookupError(f"day {the_date} not found")


def _day_row(goal_plan: dict, the_date: str):
    return next(item for item in goal_plan["daily_plan"] if str(item[0])[:10] == the_date)


def _stamped_leg_ids(checkpoint: dict) -> dict:
    """Сессии дня как их заставили в этом сохранённом чекпоинте (правило #205)."""
    plan = restore_goal_plan_from_checkpoint(checkpoint)
    template = _day_template(plan, TARGET)
    return {
        str(s.get("sport")): str(s.get("session_id"))
        for s in list(template.get("sessions") or [])
        if isinstance(s, dict) and s.get("session_id")
    }


@pytest.fixture()
def db(tmp_path):
    return Database(str(tmp_path / "retract.db"))


@pytest.fixture()
def chained(db):
    """A: исходный план; B: потомок, где день схлопнут ограничением."""
    a_saved = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    b_plan = with_checkpoint_provenance(
        _collapsed_plan(),
        source="coach_constraint",
        parent_checkpoint_id=a_saved["id"],
    )
    b_saved = db.save_planning_checkpoint(build_planning_checkpoint(b_plan))
    return a_saved, b_saved


def test_recover_restores_original_legs_with_donor_provenance(db, chained):
    from api.planning_service import recover_day_after_constraint_retraction

    a_saved, b_saved = chained
    # Идентичность ног — та, что заставлена в донорском чекпоинте A.
    leg_ids = _stamped_leg_ids(a_saved)
    bike_id = leg_ids["bike"]

    result = recover_day_after_constraint_retraction(
        db,
        base_checkpoint_id=b_saved["id"],
        date=TARGET,
        exclude_sports=("swim",),
    )

    assert result["changed"] is True
    restored = sorted(result["restored_session_ids"])
    assert len(restored) == 1
    # Вело-нога вернулась (контент идентичен донору); при схлопывании дня с двух
    # ног до одной движок идентичностей (#205) переставляет её на день-идентичность,
    # и переход фиксируется явно.
    if restored[0] == bike_id:
        assert not result["session_id_handoffs"]
    else:
        assert result["session_id_handoffs"].get(bike_id) == restored[0]
    assert result["donor_checkpoint_id"] == a_saved["id"]
    assert result["applied_checkpoint_id"]

    child = db.get_planning_checkpoint(result["applied_checkpoint_id"])
    provenance = (child.get("checkpoint_source"), child.get("checkpoint_parent_id"))
    assert provenance == ("constraint_repair", b_saved["id"])

    child_plan = restore_goal_plan_from_checkpoint(child)
    template = _day_template(child_plan, TARGET)
    legs = list(template.get("sessions") or [])
    # Вело-нога одна, плавание отсутствует; контентный fingerprint сохранён от донора.
    assert [str(s.get("sport")) for s in legs] == ["bike"]
    assert legs[0]["materialized_steps"] == [{"name": "steady"}]
    assert float(template["allocated_parts"]["bike"]) == 36.5
    assert float(template.get("allocated_parts", {}).get("swim") or 0) == 0.0
    evidence = template.get("repair_evidence")
    assert evidence and evidence.get("donor_checkpoint_id") == a_saved["id"]
    assert evidence.get("excluded_sports") == ["swim"]

    row = _day_row(child_plan, TARGET)
    assert float(row[1]) == 36.5
    assert float(row[2].get("bike") or 0) == 36.5
    assert float(row[2].get("swim") or 0) == 0.0
    # Соседние дни не задеты.
    assert float(_day_row(child_plan, "2026-08-17")[1]) == 30.0
    assert float(_day_row(child_plan, "2026-08-19")[1]) == 25.0
    # Недельные суммы пересчитаны: 30 + 36.5 + 25 = 91.5 -> 92.
    weekly_rows = list(child_plan.get("weekly_summary") or [])
    assert int(round(float(weekly_rows[0]["weekly_tss"]))) == 92


def test_rerecover_rebinds_preserved_plan_fact_matches(db, chained):
    """Подтверждённый матч возвращённой ноги переупутывается на ставшийся id (#473/M1)."""
    import hashlib

    from api.planning_service import recover_day_after_constraint_retraction

    a_saved, b_saved = chained
    bike_id = _stamped_leg_ids(a_saved)["bike"]

    fingerprint = hashlib.sha256(b"test-match-a").hexdigest()
    db.save_plan_actual_match(
        {
            "fingerprint": fingerprint,
            "target_key": f"session:{bike_id}",
            "base_checkpoint_id": int(b_saved["id"]),
            "session_date": TARGET,
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "planned_snapshot": {"session_id": bike_id, "date": TARGET, "sport": "indoor_cycling", "tss": 36.5},
            "actual_activity_ids": ["24026706443"],
            "actual_snapshot": {"activity_id": "24026706443", "tss": 28.2},
            "evidence": [],
            "rule_version": "plan_actual_match_v1",
            "session_id": bike_id,
        }
    )

    result = recover_day_after_constraint_retraction(
        db,
        base_checkpoint_id=b_saved["id"],
        date=TARGET,
        exclude_sports=("swim",),
    )
    stamped_id = result["restored_session_ids"][0]

    ledger = db.get_latest_plan_actual_matches(start_date=TARGET, end_date=TARGET)
    rebound = next((r for r in ledger if str(r.get("target_key")) == f"session:{stamped_id}"), None)
    assert rebound, "confirming mat ch was not re-point to re-stamped id"
    assert "24026706443" in list(rebound.get("actual_activity_ids") or [])
    assert rebound.get("supersedes_match_id")


def test_recover_without_exclusions_restores_all_legs(db, chained):
    from api.planning_service import recover_day_after_constraint_retraction

    a_saved, b_saved = chained
    leg_ids = _stamped_leg_ids(a_saved)

    result = recover_day_after_constraint_retraction(
        db,
        base_checkpoint_id=b_saved["id"],
        date=TARGET,
    )

    assert result["changed"] is True
    assert sorted(result["restored_session_ids"]) == sorted([leg_ids["bike"], leg_ids["swim"]])


def test_recover_on_repaired_day_is_noop(db, chained):
    from api.planning_service import recover_day_after_constraint_retraction

    _a_saved, b_saved = chained
    first = recover_day_after_constraint_retraction(
        db,
        base_checkpoint_id=b_saved["id"],
        date=TARGET,
        exclude_sports=("swim",),
    )
    assert first["changed"] is True

    # Повторный вызов поверх уже восстановленного дня: ничего не меняется, ничего не сохраняется.
    repeat = recover_day_after_constraint_retraction(
        db,
        base_checkpoint_id=first["applied_checkpoint_id"],
        date=TARGET,
        exclude_sports=("swim",),
    )
    assert repeat["changed"] is False
    assert repeat["applied_checkpoint_id"] is None
    assert repeat["reason"]


def test_recover_rejects_stale_base(db, chained):
    from api.planning_service import StalePlanningCheckpointError, recover_day_after_constraint_retraction

    _a_saved, b_saved = chained

    with pytest.raises(StalePlanningCheckpointError):
        recover_day_after_constraint_retraction(
            db,
            base_checkpoint_id=b_saved["id"] + 999,
            date=TARGET,
            exclude_sports=("swim",),
        )


def test_repair_day_route_rejects_stale_base(db, chained):
    """POST /api/planning/repair-day: запрошенный base не подменяется молча latest (#473)."""
    from fastapi import HTTPException

    from api.routers import planning as planning_router

    _a_saved, b_saved = chained
    req = planning_router.RepairDayRequest(
        date=TARGET,
        exclude_sports=["swim"],
        base_checkpoint_id=b_saved["id"] + 999,
    )
    with pytest.raises(HTTPException) as excinfo:
        planning_router.repair_day(req, db=db)
    assert excinfo.value.status_code == 409
    # База не изменена: новых чекпоинтов не появилось.
    assert db.get_latest_planning_checkpoint()["id"] == b_saved["id"]


def test_recover_raises_when_no_executable_ancestor_exists(db):
    from api.planning_service import NoDonorCheckpointError, recover_day_after_constraint_retraction

    # Корень и потомок несут день уже в офф-состоянии: исполняемой версии ни у кого нет.
    root = _collapsed_plan()
    root_saved = db.save_planning_checkpoint(build_planning_checkpoint(root))
    child_saved = db.save_planning_checkpoint(
        build_planning_checkpoint(
            with_checkpoint_provenance(
                deepcopy(root),
                source="manual_edit",
                parent_checkpoint_id=root_saved["id"],
            )
        )
    )
    with pytest.raises(NoDonorCheckpointError) as excinfo:
        recover_day_after_constraint_retraction(
            db,
            base_checkpoint_id=child_saved["id"],
            date=TARGET,
            exclude_sports=("swim",),
        )
    assert TARGET in str(excinfo.value)
    # Ничего не сохранено.
    assert db.get_latest_planning_checkpoint()["id"] == child_saved["id"]


def test_retract_route_deactivates_constraint_and_repairs_day(db, chained):
    """POST /api/planning/constraints/{id}/retract: деактивация + примитив одним вызовом."""
    from api.routers import planning as planning_router

    a_saved, b_saved = chained
    leg_ids = _stamped_leg_ids(a_saved)
    constraint = db.save_coach_constraint(date=TARGET, kind="unavailable", source="coach")

    payload = planning_router.retract_constraint(constraint_id=int(constraint["id"]), db=db)

    assert payload["constraint"]["status"] == "inactive"
    assert payload["recover"]["applied_checkpoint_id"]
    # Whole-day ограничение (без sport) → восстановление обеих ног донора.
    assert sorted(payload["recover"]["restored_session_ids"]) == sorted([leg_ids["bike"], leg_ids["swim"]])


def test_retract_route_unknown_constraint_404(tmp_path):
    from fastapi import HTTPException

    from api.routers import planning as planning_router

    class _StubDB(Database):
        def get_coach_constraint(self, constraint_id):
            return None

    stub = _StubDB(str(tmp_path / "stub.db"))
    with pytest.raises(HTTPException) as excinfo:
        planning_router.retract_constraint(constraint_id=4242, db=stub)
    assert excinfo.value.status_code == 404

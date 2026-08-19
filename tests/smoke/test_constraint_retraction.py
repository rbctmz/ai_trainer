"""Smoke tests for day recovery after constraint retraction (issue #473, M3)."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

import pytest

from data.database import Database
from models.coach_constraints import apply_constraints_to_goal_plan
from models.planning_checkpoints import build_planning_checkpoint, restore_goal_plan_from_checkpoint


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
                        "session_id": "atts_bike_orig",
                        "sport": "bike",
                        "total_tss": 36.5,
                        "duration_minutes": 40,
                        "template_key": "bike_aerobic_endurance",
                        "materialization_status": "materialized",
                        "materialized_steps": [{"name": "steady"}],
                        "definition_snapshot": {"template_key": "bike_aerobic_endurance"},
                    },
                    {
                        "session_id": "atts_swim_orig",
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
    return next(t for t in goal_plan["session_templates"] if str(t.get("date"))[:10] == the_date)


def _day_row(goal_plan: dict, the_date: str):
    return next(item for item in goal_plan["daily_plan"] if str(item[0])[:10] == the_date)


@pytest.fixture()
def db(tmp_path):
    return Database(str(tmp_path / "retract.db"))


def test_recover_restores_original_legs_with_donor_provenance(db):
    from api.planning_service import recover_day_after_constraint_retraction

    # A: исходный план с двумя ногами; B: потомок, где день схлопнут ограничением.
    a_saved = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    from models.planning_checkpoints import with_checkpoint_provenance

    b_plan = with_checkpoint_provenance(
        _collapsed_plan(),
        source="coach_constraint",
        parent_checkpoint_id=a_saved["id"],
    )
    b_saved = db.save_planning_checkpoint(build_planning_checkpoint(b_plan))

    result = recover_day_after_constraint_retraction(
        db,
        base_checkpoint_id=b_saved["id"],
        date=TARGET,
        exclude_sports=("swim",),
    )

    assert result["changed"] is True
    assert sorted(result["restored_session_ids"]) == ["atts_bike_orig"]
    assert result["donor_checkpoint_id"] == a_saved["id"]
    assert result["applied_checkpoint_id"]

    child = db.get_planning_checkpoint(result["applied_checkpoint_id"])
    provenance = (child.get("checkpoint_source"), child.get("checkpoint_parent_id"))
    assert provenance == ("constraint_repair", b_saved["id"])

    child_plan = restore_goal_plan_from_checkpoint(child)
    template = _day_template(child_plan, TARGET)
    legs = list(template.get("sessions") or [])
    # Вело-нога вернулась с оригинальными идентичностью и шагами; плавание отсутствует.
    assert [s["session_id"] for s in legs] == ["atts_bike_orig"]
    assert legs[0]["materialized_steps"] == [{"name": "steady"}]
    assert float(template["allocated_parts"]["bike"]) == 36.5
    assert "swim" not in template.get("allocated_parts") or float(template["allocated_parts"].get("swim") or 0) == 0.0
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


def test_recover_without_exclusions_restores_all_legs(db):
    from api.planning_service import recover_day_after_constraint_retraction

    a_saved = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    from models.planning_checkpoints import with_checkpoint_provenance

    b_saved = db.save_planning_checkpoint(
        build_planning_checkpoint(
            with_checkpoint_provenance(
                _collapsed_plan(),
                source="coach_constraint",
                parent_checkpoint_id=a_saved["id"],
            )
        )
    )

    result = recover_day_after_constraint_retraction(
        db,
        base_checkpoint_id=b_saved["id"],
        date=TARGET,
    )

    assert result["changed"] is True
    assert sorted(result["restored_session_ids"]) == ["atts_bike_orig", "atts_swim_orig"]


def test_recover_on_repaired_day_is_noop(db):
    from api.planning_service import recover_day_after_constraint_retraction

    a_saved = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    from models.planning_checkpoints import with_checkpoint_provenance

    b_saved = db.save_planning_checkpoint(
        build_planning_checkpoint(
            with_checkpoint_provenance(
                _collapsed_plan(),
                source="coach_constraint",
                parent_checkpoint_id=a_saved["id"],
            )
        )
    )
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


def test_recover_rejects_stale_base(db):
    from api.planning_service import StalePlanningCheckpointError, recover_day_after_constraint_retraction

    a_saved = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    from models.planning_checkpoints import with_checkpoint_provenance

    b_saved = db.save_planning_checkpoint(
        build_planning_checkpoint(
            with_checkpoint_provenance(
                _collapsed_plan(),
                source="coach_constraint",
                parent_checkpoint_id=a_saved["id"],
            )
        )
    )
    with pytest.raises(StalePlanningCheckpointError):
        recover_day_after_constraint_retraction(
            db,
            base_checkpoint_id=b_saved["id"] + 99,
            date=TARGET,
            exclude_sports=("swim",),
        )


def test_recover_raises_when_no_executable_ancestor_exists(db):
    from api.planning_service import NoDonorCheckpointError, recover_day_after_constraint_retraction

    # Корень и потомок несут день уже в офф-состоянии (план построен до ограничения):
    # исполняемой версии дня ни у кого нет — только явная ошибка.
    root = _collapsed_plan()
    root_saved = db.save_planning_checkpoint(build_planning_checkpoint(root))
    from models.planning_checkpoints import with_checkpoint_provenance

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


def test_retract_route_deactivates_constraint_and_repairs_day(db):
    """POST /api/planning/constraints/{id}/retract: деактивация + примитив одним вызовом."""
    from api.routers import planning as planning_router
    from models.planning_checkpoints import with_checkpoint_provenance

    a_saved = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    b_saved = db.save_planning_checkpoint(
        build_planning_checkpoint(
            with_checkpoint_provenance(
                _collapsed_plan(),
                source="coach_constraint",
                parent_checkpoint_id=a_saved["id"],
            )
        )
    )
    constraint = db.save_coach_constraint(date=TARGET, kind="unavailable", source="coach")

    payload = planning_router.retract_constraint(constraint_id=int(constraint["id"]), db=db)

    assert payload["constraint"]["status"] == "inactive"
    assert payload["recover"]["applied_checkpoint_id"]
    assert payload["recover"]["restored_session_ids"] == ["atts_bike_orig"]


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

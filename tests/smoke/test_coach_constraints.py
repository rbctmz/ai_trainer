"""Smoke tests for durable coach/planning constraints."""
from __future__ import annotations

from datetime import datetime, timedelta

from data.database import Database


def _date(offset: int = 0) -> str:
    return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _goal_plan() -> dict:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_plan = []
    templates = []
    for i in range(3):
        dt = today + timedelta(days=i)
        daily_plan.append((dt, 40.0 + i * 5, {"bike": 40.0 + i * 5}))
        templates.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "session_role": "quality" if i == 1 else "easy",
                "sport": "bike",
                "export_name": f"Bike day {i}",
                "duration_minutes": 60,
            }
        )
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "daily_plan": daily_plan,
        "session_templates": templates,
    }


def test_database_persists_and_filters_active_coach_constraints(tmp_path):
    db = Database(str(tmp_path / "constraints.db"))
    today = _date()
    tomorrow = _date(1)

    sick = db.save_coach_constraint(
        date=today,
        kind="sick",
        source="user",
        note="Температура, без тренировок",
        plan_id="plan-1",
        session_id="session-1",
        metadata={"severity": "high"},
    )
    unavailable = db.save_coach_constraint(
        date=tomorrow,
        kind="unavailable",
        source="coach",
        note="Перелёт",
    )

    assert sick["id"]
    assert sick["status"] == "active"
    assert sick["kind"] == "sick"
    assert sick["metadata"]["severity"] == "high"

    active = db.get_coach_constraints(start_date=today, end_date=tomorrow)
    assert [row["id"] for row in active] == [sick["id"], unavailable["id"]]

    deactivated = db.deactivate_coach_constraint(sick["id"])
    assert deactivated["status"] == "inactive"
    assert deactivated["resolved_at"]

    active_after = db.get_coach_constraints(start_date=today, end_date=tomorrow)
    assert [row["id"] for row in active_after] == [unavailable["id"]]

    all_rows = db.get_coach_constraints(start_date=today, end_date=tomorrow, active_only=False)
    assert {row["id"] for row in all_rows} == {sick["id"], unavailable["id"]}


def test_planning_status_exposes_active_constraints(tmp_path):
    from api.routers.planning import planning_status

    db = Database(str(tmp_path / "planning_constraints.db"))
    db.save_coach_constraint(date=_date(), kind="forced_rest", source="coach", note="Восстановление")

    payload = planning_status(db=db)

    assert payload["active_constraint_count"] == 1
    assert payload["active_constraints"][0]["kind"] == "forced_rest"
    assert payload["active_constraints"][0]["note"] == "Восстановление"


def test_planning_constraint_api_create_list_and_deactivate(tmp_path):
    from api.routers import planning as planning_router

    db = Database(str(tmp_path / "api_constraints.db"))
    req = planning_router.ConstraintRequest(
        date=_date(),
        kind="manual_delete",
        source="user",
        note="Убрал тренировку вручную",
        plan_id="plan-42",
        session_id="day-0",
        metadata={"origin": "calendar"},
    )

    created = planning_router.create_constraint(req, db=db)
    assert created["kind"] == "manual_delete"
    assert created["metadata"]["origin"] == "calendar"

    listed = planning_router.list_constraints(days=7, db=db)
    assert listed["count"] == 1
    assert listed["constraints"][0]["id"] == created["id"]

    deactivated = planning_router.deactivate_constraint(created["id"], db=db)
    assert deactivated["status"] == "inactive"

    listed_after = planning_router.list_constraints(days=7, db=db)
    assert listed_after["count"] == 0


def test_planning_constraint_routes_registered():
    import importlib

    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert {
        "/api/planning/constraints",
        "/api/planning/constraints/{constraint_id}",
    } <= paths


def test_apply_constraints_to_goal_plan_marks_matching_days_protected():
    from models.coach_constraints import apply_constraints_to_goal_plan

    plan = _goal_plan()
    target_date = plan["daily_plan"][1][0].strftime("%Y-%m-%d")
    constraints = [
        {
            "id": 10,
            "date": target_date,
            "kind": "sick",
            "source": "user",
            "note": "Болею",
            "status": "active",
        }
    ]

    updated, summary = apply_constraints_to_goal_plan(plan, constraints)

    assert summary["applied_count"] == 1
    assert summary["protected_dates"] == [target_date]
    assert plan["daily_plan"][1][1] > 0  # input plan is not mutated
    assert updated["daily_plan"][0][1] > 0
    assert updated["daily_plan"][1][1] == 0
    assert updated["daily_plan"][1][2] == {"bike": 0.0}
    assert updated["daily_plan"][2][1] > 0
    protected_template = updated["session_templates"][1]
    assert protected_template["session_role"] == "off"
    assert protected_template["protected_by_constraint"] is True
    assert protected_template["constraint"]["kind"] == "sick"

"""Smoke tests for durable coach/planning constraints."""
from __future__ import annotations

from copy import deepcopy
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
    plan["session_templates"][1].update(
        {
            "kind": "composite",
            "template_key": "brick_endurance",
            "materialization_status": "materialized",
            "definition_snapshot": {"template_key": "brick_endurance"},
            "materialized_steps": [],
            "legs": [{"sport": "bike"}, {"sport": "run"}],
            "prescription_fingerprint": "stale-if-kept",
        }
    )
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
    assert protected_template["sport"] == "off"
    assert protected_template["template_key"] == "constraint:sick"
    assert protected_template["materialization_status"] == "constraint_off"
    assert "definition_snapshot" not in protected_template
    assert "legs" not in protected_template
    assert "prescription_fingerprint" not in protected_template
    assert protected_template["protected_by_constraint"] is True
    assert protected_template["constraint"]["kind"] == "sick"


# --- Scoped (per-sport) constraints — issue #473 ---------------------------


def _two_leg_plan() -> dict:
    """Два дня: цель с двумя ногами (вело + плавание) и соседний день-контроль."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    target_day = today + timedelta(days=2)
    bike_session = {
        "session_id": "atts_bike_1",
        "sport": "bike",
        "sport_label": "вело",
        "session_role": "easy",
        "session_focus": "Aerobic Endurance Ride",
        "total_tss": 36.5,
        "duration_minutes": 40,
        "template_key": "bike_aerobic_endurance",
        "materialization_status": "materialized",
        "materialized_steps": [{"name": "a"}],
        "definition_snapshot": {"template_key": "bike_aerobic_endurance"},
    }
    swim_session = {
        "session_id": "atts_swim_1",
        "sport": "swim",
        "sport_label": "плавание",
        "session_role": "easy",
        "session_focus": "Swim Endurance",
        "total_tss": 27.5,
        "duration_minutes": 35,
        "template_key": "swim_endurance",
        "materialization_status": "materialized",
        "materialized_steps": [{"name": "a"}],
        "definition_snapshot": {"template_key": "swim_endurance"},
    }
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "daily_plan": [
            (today, 30.0, {"run": 30.0}),
            (today + timedelta(days=1), 25.0, {"run": 25.0}),
            (target_day, 64.0, {"bike": 36.5, "swim": 27.5}),
        ],
        "session_templates": [
            {
                "date": today.strftime("%Y-%m-%d"),
                "session_role": "easy",
                "sport": "run",
                "duration_minutes": 45,
                "sessions": [
                    {
                        "session_id": "atts_run_x",
                        "sport": "run",
                        "total_tss": 30.0,
                        "duration_minutes": 45,
                        "materialization_status": "materialized",
                        "materialized_steps": [],
                    }
                ],
            },
            {
                "date": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
                "session_role": "easy",
                "sport": "run",
                "duration_minutes": 40,
                "sessions": [
                    {
                        "session_id": "atts_run_y",
                        "sport": "run",
                        "total_tss": 25.0,
                        "duration_minutes": 40,
                        "materialization_status": "materialized",
                        "materialized_steps": [],
                    }
                ],
            },
            {
                "date": target_day.strftime("%Y-%m-%d"),
                "week_index": 0,
                "day_index": 2,
                "phase": "Base",
                "session_role": "easy",
                "sport": "bike",
                # Общая длительность дня = сумма ног (40 вело + 35 плавание),
                # чтобы в partial-пути было видно пересчёт после удаления ноги.
                "duration_minutes": 75,
                "allocated_parts": {"bike": 36.5, "swim": 27.5},
                "sessions": [deepcopy(bike_session), deepcopy(swim_session)],
            },
        ],
        "weekly_summary": [
            {"week_start": today.strftime("%Y-%m-%d"), "weekly_tss": 119, "bike": 36.5, "swim": 27.5, "run": 55.0}
        ],
    }


def _leg_sessions(template: dict) -> list[dict]:
    return list(template.get("sessions") or [])


def test_per_sport_constraint_kills_only_that_leg():
    from models.coach_constraints import apply_constraints_to_goal_plan

    plan = _two_leg_plan()
    target_date = plan["session_templates"][2]["date"]
    planned = deepcopy(plan)
    constraint = {
        "id": 21,
        "date": target_date,
        "kind": "unavailable",
        "source": "coach",
        "note": "Плавание отменено пользователем",
        "status": "active",
        "sport": "swim",
    }

    updated, summary = apply_constraints_to_goal_plan(planned, [constraint])

    target_row = next(
        (item for item in updated["daily_plan"] if str(item[0])[:10] == target_date),
        None,
    )
    template = next(t for t in updated["session_templates"] if str(t.get("date"))[:10] == target_date)
    # Вело-нога жива с сохранённым идентификатором и шагами.
    kept = _leg_sessions(template)
    assert [s["session_id"] for s in kept] == ["atts_bike_1"]
    assert kept[0]["materialization_status"] == "materialized"
    assert kept[0].get("materialized_steps") == [{"name": "a"}]
    # Дневной груз пересчитан только по вело.
    assert float(target_row[1]) == 36.5
    assert float(target_row[2]["bike"]) == 36.5
    assert float(target_row[2]["swim"]) == 0.0
    assert float(template["allocated_parts"]["swim"]) == 0.0
    assert float(template["allocated_parts"]["bike"]) == 36.5
    # Дневная длительность пересчитана по выжившим ногам (75 -> 40), иначе карточка
    # дня показывает груз несуществующего плавания (review #2 к M2 GREEN).
    assert float(template.get("duration_minutes") or 0) == 40.0
    # Аудит вычеркнутой ноги: id/спорт/груз и причина (какое ограничение) видны
    # из метаданных шаблона — по дате восстанавливать «чем вызвано» не нужно.
    canceled = template.get("canceled_legs")
    assert canceled and len(canceled) == 1, f"canceled_legs missing: {canceled}"
    assert canceled[0]["session_id"] == "atts_swim_1"
    assert canceled[0]["sport"] == "swim"
    assert float(canceled[0]["total_tss"]) == 27.5
    assert canceled[0]["constraint_id"] == 21
    assert canceled[0]["kind"] == "unavailable"
    assert canceled[0]["note"] == "Плавание отменено пользователем"
    # Недельные суммы пересчитаны по обновлённому дневному плану.
    expected_total = int(round(sum(float(item[1]) for item in updated["daily_plan"])))
    assert expected_total == int(round(30.0 + 36.5 + 25.0))
    week_rows = list(updated["weekly_summary"])
    assert week_rows
    assert int(round(float(week_rows[0]["weekly_tss"]))) == expected_total
    assert float(week_rows[0].get("swim", 0.0)) == 0.0
    assert float(week_rows[0].get("bike", 0.0)) == 36.5
    # Соседние дни не тронуты.
    other_rows = [
        item for item in updated["daily_plan"] if str(item[0])[:10] != target_date
    ]
    assert sorted(float(item[1]) for item in other_rows) == [25.0, 30.0]
    # Неизменный входной план не мутирован.
    input_template = next(t for t in planned["session_templates"] if str(t.get("date"))[:10] == target_date)
    assert len(_leg_sessions(input_template)) == 2


def test_whole_day_constraint_still_zeros_everything_regression():
    from models.coach_constraints import apply_constraints_to_goal_plan

    plan = _two_leg_plan()
    target_date = plan["session_templates"][2]["date"]
    constraint = {
        "id": 22,
        "date": target_date,
        "kind": "sick",
        "source": "user",
        "note": "Болею",
        "status": "active",
    }

    updated, summary = apply_constraints_to_goal_plan(plan, [constraint])

    template = next(t for t in updated["session_templates"] if str(t.get("date"))[:10] == target_date)
    target_row = next(
        (item for item in updated["daily_plan"] if str(item[0])[:10] == target_date),
        None,
    )
    assert _leg_sessions(template) == []
    assert template["materialization_status"] == "constraint_off"
    assert float(target_row[1]) == 0.0


def test_two_per_sport_constraints_collapse_day_to_off():
    from models.coach_constraints import apply_constraints_to_goal_plan

    plan = _two_leg_plan()
    target_date = plan["session_templates"][2]["date"]
    constraints = [
        {"id": 31, "date": target_date, "kind": "unavailable", "source": "coach", "status": "active", "sport": "swim"},
        {"id": 32, "date": target_date, "kind": "unavailable", "source": "coach", "status": "active", "sport": "bike"},
    ]

    updated, _ = apply_constraints_to_goal_plan(plan, constraints)

    template = next(t for t in updated["session_templates"] if str(t.get("date"))[:10] == target_date)
    target_row = next(
        (item for item in updated["daily_plan"] if str(item[0])[:10] == target_date),
        None,
    )
    assert _leg_sessions(template) == []
    assert template["materialization_status"] == "constraint_off"
    assert float(target_row[1]) == 0.0


def test_composite_day_falls_back_to_whole_day_zeroing():
    from models.coach_constraints import apply_constraints_to_goal_plan

    plan = _two_leg_plan()
    target_date = plan["session_templates"][2]["date"]
    target_template = next(t for t in plan["session_templates"] if str(t.get("date"))[:10] == target_date)
    target_template["kind"] = "composite"
    target_template["template_key"] = "brick_endurance"
    constraint = {
        "id": 33,
        "date": target_date,
        "kind": "unavailable",
        "source": "coach",
        "status": "active",
        "sport": "swim",
    }

    updated, _ = apply_constraints_to_goal_plan(plan, [constraint])

    rebuilt = next(t for t in updated["session_templates"] if str(t.get("date"))[:10] == target_date)
    target_row = next(
        (item for item in updated["daily_plan"] if str(item[0])[:10] == target_date),
        None,
    )
    assert _leg_sessions(rebuilt) == []
    assert rebuilt["materialization_status"] == "constraint_off"
    assert float(target_row[1]) == 0.0


def test_database_persists_and_normalizes_constraint_sport(tmp_path):
    db = Database(str(tmp_path / "constraints_sport.db"))
    row = db.save_coach_constraint(
        date=_date(), kind="unavailable", source="coach", note="Закрытие бассейна", sport="плавание"
    )
    assert row["sport"] == "swim", f"sport normalization broken: {row['sport']!r}"

    empty = db.save_coach_constraint(date=_date(1), kind="sick", source="coach")
    assert empty["sport"] in (None, ""), f"whole-day sport must stay empty: {empty['sport']!r}"

    listed = db.get_coach_constraints(start_date=_date(-1), end_date=_date(3))
    by_id = {r["id"]: r for r in listed}
    assert by_id[row["id"]]["sport"] == "swim"
    assert by_id[empty["id"]]["sport"] in (None, "")


def test_save_coach_constraint_rejects_unknown_sport(tmp_path):
    db = Database(str(tmp_path / "constraints_bad_sport.db"))
    try:
        db.save_coach_constraint(date=_date(), kind="sick", source="coach", sport="flying")
    except ValueError:
        return
    raise AssertionError("unknown sport must be rejected with ValueError")


def test_per_sport_constraint_does_not_block_rebalance_day(tmp_path):
    """BDD (#473): ограничение одной ноги не закрывает день от ребаланса нагрузки."""
    from api.planning_service import _rebalance_protected_dates

    db = Database(str(tmp_path / "rebalance_scope.db"))
    today = datetime.now().date()
    scope_day = (today + timedelta(days=3)).isoformat()
    whole_day = (today + timedelta(days=4)).isoformat()
    db.save_coach_constraint(date=scope_day, kind="unavailable", source="coach", sport="swim")
    db.save_coach_constraint(date=whole_day, kind="sick", source="coach")

    goal_plan = {"protected_dates": [], "constraint_summary": {}}
    protected = _rebalance_protected_dates(db, goal_plan, as_of=today)

    assert whole_day in protected
    assert scope_day not in protected


def test_constraint_request_validates_sport_at_api_layer():
    """Безизвестный спорт падает валидацией запроса (HTTP 422), алиас мапится в канон."""
    import pydantic

    from api.routers import planning as planning_router

    try:
        planning_router.ConstraintRequest(
            date=_date(), kind="sick", source="user", sport="flying"
        )
    except pydantic.ValidationError:
        pass
    else:
        raise AssertionError("unknown sport must fail request validation (422)")

    aliased = planning_router.ConstraintRequest(
        date=_date(), kind="unavailable", source="user", sport="плавание"
    )
    assert aliased.sport == "swim"
    whole = planning_router.ConstraintRequest(date=_date(), kind="sick", source="user")
    assert whole.sport is None

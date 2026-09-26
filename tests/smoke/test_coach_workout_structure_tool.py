"""Контракт issue #638: Коуч видит структуру плановой тренировки.

Дефект: `get_upcoming_workouts` проецирует шаблон сессии в скалярные поля и
отбрасывает `materialized_steps`, а презентер их не рендерит — модель видит
только `formatted_result`. В вакууме Коуч подставлял общие знания и подавал их
как план (в чате от 26.09 — «4–5 × 1 мин» вместо фактических отрезков плана).

Контракт среза:
* структура отдаётся через существующую проекцию
  `models/plan_intervals.project_planned_intervals` — новой не пишем;
* `get_upcoming_workouts` отдаёт дешёвые `has_structure`/`structure_status`
  без шагов (payload окна не должен расти);
* презентер рендерит структуру в `formatted_result`, иначе модель её не увидит;
* сессия без шагов честно называет причину: день отдыха — это НЕ «структура не
  материализована», а неизвестная структура — не пустой список;
* пользовательский текст идёт по `segment_kind`, а не по `type` — у разминки и
  заминки `type == "rest"` (семантика матчинга), и разминка не должна
  отрендериться как «отдых».

Форма фикстуры выверена по живому плану: шаги есть у всех тренировочных сессий,
включая плавание (`structure_status=legacy_pattern`, 3–4 шага); без шагов
остаются только дни отдыха (`session_role=off`) и дни с неудавшейся
материализацией.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from data.database import Database
from models.ai_tools import AITools
from models.coach_tool_presenter import format_tool_result
from models.planning_checkpoints import build_planning_checkpoint
from models.workout_catalog import materialize_session_template


pytestmark = pytest.mark.smoke

_STRUCTURED_DATE = date.today()
_UNMATERIALIZED_DATE = date.today() + timedelta(days=1)
_REST_DATE = date.today() + timedelta(days=2)


def _goal_plan() -> dict:
    """План на три сессии: структурированная, без структуры и день отдыха."""
    start_week = date.today() - timedelta(days=date.today().weekday())
    structured = dict(
        materialize_session_template(
            phase="Taper",
            session_role="long",
            sport="bike",
            target_tss=50.0,
            estimated_duration_minutes=120,
            goal_type="Триатлон",
            zone_snapshot={"ftp": 200},
        )
    )
    structured.update(
        {
            "date": _STRUCTURED_DATE.isoformat(),
            "phase": "Taper",
            "sport": "bike",
            "sport_label": "вело",
            "session_focus": "VO2max Intervals",
            "export_name": "Тест — VO2max Intervals",
            "session_role": "long",
        }
    )
    # Сессия без шагов и без заявленного статуса: материализация не удалась.
    unmaterialized = {
        "date": _UNMATERIALIZED_DATE.isoformat(),
        "phase": "Taper",
        "sport": "bike",
        "sport_label": "вело",
        "session_focus": "Aerobic Endurance",
        "export_name": "Тест — Aerobic Endurance",
        "session_role": "easy",
        "materialization_status": "legacy_role_fallback",
    }
    rest = {
        "date": _REST_DATE.isoformat(),
        "phase": "Taper",
        "sport": "off",
        "sport_label": "отдых",
        "session_focus": "Отдых",
        "export_name": "Тест — Отдых",
        "session_role": "off",
    }
    event_date = start_week + timedelta(weeks=8)

    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "event_date": event_date.isoformat(),
        "events": [
            {"date": event_date.isoformat(), "priority": "A", "label": "Старт"}
        ],
        "weeks_to_race": 8,
        "start_week": start_week,
        "weekly_tss_plan": [300] * 8,
        "base_weekly_tss_plan": [300] * 8,
        "phases": ["Taper"] * 8,
        "daily_plan": [
            (datetime.combine(_STRUCTURED_DATE, datetime.min.time()), 50, {"bike": 50.0}),
            (datetime.combine(_UNMATERIALIZED_DATE, datetime.min.time()), 30, {"bike": 30.0}),
            (datetime.combine(_REST_DATE, datetime.min.time()), 0, {}),
        ],
        "session_templates": [structured, unmaterialized, rest],
        "weekly_summary": [],
        "constraint_summary": {
            "load_state": "balanced",
            "available_day_indices": list(range(7)),
            "notes": [],
        },
        "planner_mix": None,
        "planner_weights": None,
        "plan_revision": datetime.now().isoformat(),
        "near_term_edit_version": 0,
        "near_term_edit_rollback_target_checkpoint_id": None,
    }


@pytest.fixture()
def tools_with_structure(tmp_path):
    db = Database(str(tmp_path / "structure.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    return AITools(db)


@pytest.fixture()
def tools_without_plan(tmp_path):
    return AITools(Database(str(tmp_path / "no-plan.db")))


def _stored_steps(tools: AITools, day: date) -> list:
    from models.planning_checkpoints import restore_goal_plan_from_checkpoint

    plan = restore_goal_plan_from_checkpoint(tools.db.get_latest_planning_checkpoint())
    for template in plan.get("session_templates") or []:
        if str(template.get("date"))[:10] == day.isoformat():
            return list(template.get("materialized_steps") or [])
    raise AssertionError(f"фикстура не содержит сессию на {day}")


# ---------------------------------------------------------------------------
# Инструмент структуры
# ---------------------------------------------------------------------------

def test_workout_structure_by_date_projects_materialized_steps(
    tools_with_structure: AITools,
) -> None:
    """Структура берётся из `materialized_steps` через существующую проекцию."""
    result = tools_with_structure.get_workout_structure(date=_STRUCTURED_DATE.isoformat())

    assert result["has_plan"] is True
    assert result["count"] == 1
    session = result["sessions"][0]
    assert session["has_structure"] is True
    assert session["structure_status"] == "structured"
    assert session["session_id"]

    stored = _stored_steps(tools_with_structure, _STRUCTURED_DATE)
    assert len(session["steps"]) == len(stored)
    # Проекция plan_intervals — плоский упорядоченный список.
    assert [step["duration_seconds"] for step in session["steps"]] == [
        step["duration_seconds"] for step in stored
    ]
    assert [step["segment_kind"] for step in session["steps"]] == [
        step["segment_kind"] for step in stored
    ]
    assert [step["type"] for step in session["steps"]] == [
        "rest" if step.get("segment_kind") in {"warmup", "cooldown", "recovery"} else "work"
        for step in stored
    ]
    # Цель доезжает до модели: тип метрики и диапазон.
    work = next(step for step in session["steps"] if step["type"] == "work")
    assert work["target_zone"]["type"] == "power"
    assert work["target_zone"]["low"] is not None
    assert work["target_zone"]["high"] is not None


def test_workout_structure_by_session_id(tools_with_structure: AITools) -> None:
    """Поиск по session_id из get_upcoming_workouts."""
    listed = tools_with_structure.get_upcoming_workouts(days=3)["sessions"]
    target = next(item for item in listed if item["date"] == _STRUCTURED_DATE.isoformat())

    result = tools_with_structure.get_workout_structure(session_id=target["session_id"])

    assert result["count"] == 1
    assert result["sessions"][0]["session_id"] == target["session_id"]
    assert len(result["sessions"][0]["steps"]) > 0


def test_workout_structure_unmaterialized_session_is_honest(
    tools_with_structure: AITools,
) -> None:
    """Неудавшаяся материализация сообщается словами, а не пустым списком."""
    result = tools_with_structure.get_workout_structure(
        date=_UNMATERIALIZED_DATE.isoformat()
    )

    session = result["sessions"][0]
    assert session["has_structure"] is False
    assert session["structure_status"] == "unmaterialized"
    assert session["steps"] == []
    assert "не материализована" in session["message"].lower()


def test_workout_structure_rest_day_is_not_missing_structure(
    tools_with_structure: AITools,
) -> None:
    """День отдыха — не «нет структуры»: тренировки в нём просто нет."""
    result = tools_with_structure.get_workout_structure(date=_REST_DATE.isoformat())

    session = result["sessions"][0]
    assert session["has_structure"] is False
    assert session["structure_status"] == "rest"
    assert "отдых" in session["message"].lower()
    assert "не материализована" not in session["message"].lower()


def test_workout_structure_unknown_date_reports_no_session(
    tools_with_structure: AITools,
) -> None:
    result = tools_with_structure.get_workout_structure(date="2099-01-01")

    assert result["count"] == 0
    assert result["message"]


def test_workout_structure_without_plan(tools_without_plan: AITools) -> None:
    result = tools_without_plan.get_workout_structure(date=_STRUCTURED_DATE.isoformat())

    assert result["has_plan"] is False
    assert result["message"]


def test_workout_structure_requires_a_lookup_key(tools_with_structure: AITools) -> None:
    """Ни дата, ни session_id не заданы — инструмент не угадывает сессию."""
    result = tools_with_structure.get_workout_structure()

    assert result["success"] is False
    assert result["error"]


def test_workout_structure_is_registered_and_callable_through_execute_tool(
    tools_with_structure: AITools,
) -> None:
    schemas = {schema["name"]: schema for schema in tools_with_structure.get_tool_schemas()}
    assert "get_workout_structure" in schemas
    assert "get_workout_structure" in tools_with_structure.tools

    outcome = tools_with_structure.execute_tool(
        "get_workout_structure", date=_STRUCTURED_DATE.isoformat()
    )

    assert outcome["success"] is True
    assert outcome["result"]["sessions"][0]["steps"]


# ---------------------------------------------------------------------------
# Дешёвый маркер в get_upcoming_workouts
# ---------------------------------------------------------------------------

def test_upcoming_workouts_exposes_structure_availability_without_steps(
    tools_with_structure: AITools,
) -> None:
    """Коуч узнаёт, где структура есть, но шаги в этот payload не едут."""
    sessions = tools_with_structure.get_upcoming_workouts(days=3)["sessions"]
    by_date = {item["date"]: item for item in sessions}

    structured = by_date[_STRUCTURED_DATE.isoformat()]
    assert structured["has_structure"] is True
    assert structured["structure_status"] == "structured"
    assert "steps" not in structured

    unmaterialized = by_date[_UNMATERIALIZED_DATE.isoformat()]
    assert unmaterialized["has_structure"] is False
    assert unmaterialized["structure_status"] == "unmaterialized"
    assert "steps" not in unmaterialized


# ---------------------------------------------------------------------------
# Презентер — именно он попадает в контекст модели
# ---------------------------------------------------------------------------

def test_presenter_renders_structure_into_formatted_result(
    tools_with_structure: AITools,
) -> None:
    """Без этого шага модель структуру не видит (см. issue #638)."""
    payload = tools_with_structure.get_workout_structure(date=_STRUCTURED_DATE.isoformat())

    rendered = format_tool_result("get_workout_structure", payload)

    session = payload["sessions"][0]
    assert session["name"] in rendered
    for step in session["steps"]:
        assert step["name"] in rendered
    # Длительность и цель каждого шага — в тексте, а не только в raw dict.
    work = next(step for step in session["steps"] if step["type"] == "work")
    assert str(work["target_zone"]["low"]) in rendered
    assert str(work["target_zone"]["high"]) in rendered


def test_presenter_labels_warmup_by_segment_kind_not_by_type(
    tools_with_structure: AITools,
) -> None:
    """У разминки `type == "rest"` — семантика матчинга, а не текст для атлета."""
    payload = tools_with_structure.get_workout_structure(date=_STRUCTURED_DATE.isoformat())
    session = payload["sessions"][0]
    warmup = next(step for step in session["steps"] if step["segment_kind"] == "warmup")
    assert warmup["type"] == "rest"

    rendered = format_tool_result("get_workout_structure", payload)

    assert "разминка" in rendered.lower()
    assert "отдых" not in rendered.lower()


def test_presenter_reports_missing_structure_honestly(
    tools_with_structure: AITools,
) -> None:
    payload = tools_with_structure.get_workout_structure(
        date=_UNMATERIALIZED_DATE.isoformat()
    )

    rendered = format_tool_result("get_workout_structure", payload)

    assert "не материализована" in rendered.lower()


def test_presenter_signals_available_structure_in_upcoming_workouts(
    tools_with_structure: AITools,
) -> None:
    """Коуч должен знать, когда углубляться, не вызывая структуру вслепую."""
    payload = tools_with_structure.get_upcoming_workouts(days=3)

    rendered = format_tool_result("get_upcoming_workouts", payload)

    assert "get_workout_structure" in rendered


def test_tool_label_is_human_readable() -> None:
    from utils.product_semantics import TOOL_LABELS_RU

    assert TOOL_LABELS_RU.get("get_workout_structure")

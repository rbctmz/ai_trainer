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

# ---------------------------------------------------------------------------
# Pace-цели беговых сессий (находка P2 независимого аудита #641)
# ---------------------------------------------------------------------------
#
# Pace-цель не несёт low/high: каталог кладёт темп в fast/slow (секунды на
# километр), а проекция plan_intervals читала только low/high — темп терялся, и
# Коуч видел в колонке цели литерал "pace" вместо чисел. В живом плане это 113
# целей из 272, то есть все беговые сессии.

_RUN_DATE = date.today() + timedelta(days=3)


def _run_goal_plan() -> dict:
    """План из одной беговой сессии с pace-целями от порогового темпа."""
    start_week = date.today() - timedelta(days=date.today().weekday())
    session = dict(
        materialize_session_template(
            phase="Race Week",
            session_role="easy",
            sport="run",
            target_tss=35.0,
            estimated_duration_minutes=40,
            goal_type="Триатлон",
            zone_snapshot={"threshold_pace": 340.0},
        )
    )
    session.update(
        {
            "date": _RUN_DATE.isoformat(),
            "phase": "Race Week",
            "sport": "run",
            "sport_label": "бег",
            "session_focus": "Аэробный бег",
            "export_name": "Тест — Recovery Run",
            "session_role": "easy",
        }
    )
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
        "phases": ["Race Week"] * 8,
        "daily_plan": [
            (datetime.combine(_RUN_DATE, datetime.min.time()), 35, {"run": 35.0}),
        ],
        "session_templates": [session],
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
def tools_with_pace(tmp_path):
    db = Database(str(tmp_path / "pace.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_run_goal_plan()))
    return AITools(db)


def test_projection_carries_run_pace_instead_of_dropping_it(
    tools_with_pace: AITools,
) -> None:
    """Темп обязан доехать до модели: у pace-цели low/high нет по конструкции."""
    payload = tools_with_pace.get_workout_structure(date=_RUN_DATE.isoformat())

    zone = payload["sessions"][0]["steps"][0]["target_zone"]
    assert zone["type"] == "pace"
    assert zone["low"] is None and zone["high"] is None
    assert zone["fast"] is not None and zone["slow"] is not None
    assert zone["fast"] < zone["slow"], "fast — меньшие секунды на км"
    assert zone["unit"] == "seconds_per_km"


def test_presenter_renders_run_pace_not_the_bare_type(
    tools_with_pace: AITools,
) -> None:
    """Регрессия аудита: в колонке цели стояло слово pace вместо темпа."""
    payload = tools_with_pace.get_workout_structure(date=_RUN_DATE.isoformat())

    rendered = format_tool_result("get_workout_structure", payload)

    assert "| pace |" not in rendered
    assert "/км" in rendered
    for step in payload["sessions"][0]["steps"]:
        zone = step["target_zone"]
        for value in (zone["fast"], zone["slow"]):
            total = int(float(value) + 0.5)
            assert f"{total // 60}:{total % 60:02d}" in rendered

# ---------------------------------------------------------------------------
# #644: нормализованный статус, граница brick-ног, единый источник маркеров
# ---------------------------------------------------------------------------

_LEGACY_DATE = date.today() + timedelta(days=4)
_BRICK_DATE = date.today() + timedelta(days=5)
_DEGENERATE_DATE = date.today() + timedelta(days=6)


def _step(name: str, seconds: int, kind: str = "work") -> dict:
    return {
        "name": name,
        "intensity": "work" if kind == "work" else "easy",
        "segment_kind": kind,
        "duration_seconds": seconds,
        "target": {"type": "power", "low": 100, "high": 120},
    }


def _edge_goal_plan() -> dict:
    """Три пограничные сессии: legacy-статус, brick-день и вырожденные шаги."""
    start_week = date.today() - timedelta(days=date.today().weekday())
    legacy = dict(
        materialize_session_template(
            phase="Taper",
            session_role="easy",
            sport="bike",
            target_tss=40.0,
            estimated_duration_minutes=60,
            goal_type="Триатлон",
            zone_snapshot={"ftp": 200},
        )
    )
    # Каталог объявляет собственный словарь статусов; инструмент обязан отдавать
    # нормализованный, а сырьё — отдельным полем (#644).
    legacy.update(
        {
            "date": _LEGACY_DATE.isoformat(),
            "phase": "Taper",
            "sport": "bike",
            "sport_label": "вело",
            "session_focus": "Recovery Spin",
            "export_name": "Тест — legacy",
            "session_role": "easy",
            "structure_status": "legacy_pattern",
        }
    )
    brick = {
        "date": _BRICK_DATE.isoformat(),
        "phase": "Build",
        "sport": "brick",
        "sport_label": "вело → бег",
        "session_focus": "Brick",
        "export_name": "Тест — brick",
        "session_role": "long",
        "kind": "composite",
        "materialized_steps": [],
        "legs": [
            {
                "leg_index": 0,
                "sport": "bike",
                "sport_label": "вело",
                "materialized_steps": [
                    _step("Warm-up", 300, "warmup"),
                    _step("Bike work", 600),
                ],
            },
            {
                "leg_index": 1,
                "sport": "run",
                "sport_label": "бег",
                "materialized_steps": [
                    _step("Run off the bike", 900),
                    _step("Cool-down", 300, "cooldown"),
                ],
            },
        ],
    }
    degenerate = {
        "date": _DEGENERATE_DATE.isoformat(),
        "phase": "Taper",
        "sport": "bike",
        "sport_label": "вело",
        "session_focus": "Broken",
        "export_name": "Тест — вырожденные шаги",
        "session_role": "easy",
        # Проекция отбрасывает шаги с duration_seconds <= 0, поэтому сырые шаги
        # и то, что реально видит Коуч, расходятся (#644).
        "materialized_steps": [_step("Zero A", 0), _step("Zero B", 0)],
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
        "phases": ["Build"] * 8,
        "daily_plan": [
            (datetime.combine(_LEGACY_DATE, datetime.min.time()), 40, {"bike": 40.0}),
            (datetime.combine(_BRICK_DATE, datetime.min.time()), 90, {"bike": 50.0, "run": 40.0}),
            (datetime.combine(_DEGENERATE_DATE, datetime.min.time()), 20, {"bike": 20.0}),
        ],
        "session_templates": [legacy, brick, degenerate],
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
def tools_with_edge_sessions(tmp_path):
    db = Database(str(tmp_path / "edge.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_edge_goal_plan()))
    return AITools(db)


def test_structure_status_is_normalized_and_keeps_the_catalog_value_as_source(
    tools_with_edge_sessions: AITools,
) -> None:
    """Имя поля обещает словарь structured/unmaterialized/rest, а не сырьё каталога."""
    payload = tools_with_edge_sessions.get_workout_structure(
        date=_LEGACY_DATE.isoformat()
    )

    session = payload["sessions"][0]
    assert session["has_structure"] is True
    assert session["structure_status"] == "structured"
    assert session["structure_source"] == "legacy_pattern"


def test_has_structure_and_steps_come_from_the_same_source(
    tools_with_edge_sessions: AITools,
) -> None:
    """Вырожденные шаги отбрасываются проекцией — маркеры обязаны совпасть."""
    payload = tools_with_edge_sessions.get_workout_structure(
        date=_DEGENERATE_DATE.isoformat()
    )

    session = payload["sessions"][0]
    assert session["steps"] == []
    assert session["has_structure"] is False
    assert session["structure_status"] == "unmaterialized"

    rendered = format_tool_result("get_workout_structure", payload)
    assert "не материализована" in rendered.lower()


def test_marker_in_upcoming_workouts_matches_the_tool(
    tools_with_edge_sessions: AITools,
) -> None:
    """Дешёвый маркер и инструмент не должны расходиться на одном и том же дне."""
    listed = tools_with_edge_sessions.get_upcoming_workouts(days=8)["sessions"]
    by_date = {item["date"]: item for item in listed}

    for day in (_LEGACY_DATE, _DEGENERATE_DATE):
        iso = day.isoformat()
        marker = by_date[iso]
        session = tools_with_edge_sessions.get_workout_structure(date=iso)["sessions"][0]
        assert marker["has_structure"] == session["has_structure"], iso
        assert marker["structure_status"] == session["structure_status"], iso


def test_brick_steps_keep_their_leg_identity(
    tools_with_edge_sessions: AITools,
) -> None:
    """Шаги вело и бега обязаны различаться: иначе brick-план не воспроизвести."""
    payload = tools_with_edge_sessions.get_workout_structure(
        date=_BRICK_DATE.isoformat()
    )

    steps = payload["sessions"][0]["steps"]
    assert [step["leg_sport"] for step in steps] == ["bike", "bike", "run", "run"]
    assert [step["leg_index"] for step in steps] == [0, 0, 1, 1]
    assert steps[0]["leg_sport_label"] == "вело"
    assert steps[2]["leg_sport_label"] == "бег"


def test_presenter_separates_brick_legs(
    tools_with_edge_sessions: AITools,
) -> None:
    payload = tools_with_edge_sessions.get_workout_structure(
        date=_BRICK_DATE.isoformat()
    )

    rendered = format_tool_result("get_workout_structure", payload)

    assert "вело" in rendered and "бег" in rendered
    # Граница ног должна быть видна в тексте, а не только в payload.
    assert rendered.count("| # |") == 2, rendered


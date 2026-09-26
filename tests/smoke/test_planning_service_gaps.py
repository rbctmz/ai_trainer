"""Закрытие слепой зоны `api/planning_service.py` (#594).

Две группы поведения, которые не проверялись: границы `export_workout` (то, что
видит роутер `/api/planning/export`) и защитные ветки `week_by_week_plan` на битых
legacy-снапшотах. Вторая группа — это ASR-REL-2: отсутствие данных даёт data gap,
а не падение.
"""
from __future__ import annotations

import copy

import pytest

from api import planning_service as ps
from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint

pytestmark = pytest.mark.smoke


def _persisted_plan(tmp_path) -> tuple[Database, dict]:
    """Активный план в temp-БД: тот же вход, которым пользуется роутер."""
    db = Database(str(tmp_path / "planning_gaps.db"))
    db.save_athlete_profile({"ftp": 200, "lthr": 165, "weight_kg": 80, "source": "test"})
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=8,
        events=[],
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )
    plan = ps.get_active_plan(db)
    assert plan is not None
    return db, plan


def _session_of(template: dict) -> dict:
    sessions = list(template.get("sessions") or [])
    return dict(sessions[0]) if sessions else dict(template)


def _find_day(plan: dict, predicate) -> int:
    for index, template in enumerate(plan.get("session_templates") or []):
        if predicate(_session_of(dict(template)), dict(template)):
            return index
    raise AssertionError("fixture has no matching day")


def test_export_workout_rejects_day_index_outside_plan(tmp_path) -> None:
    _, plan = _persisted_plan(tmp_path)

    with pytest.raises(ValueError, match="day index out of range"):
        ps.export_workout(plan, len(plan["daily_plan"]), "fit_csv")


def test_export_workout_rejects_leg_on_single_session(tmp_path) -> None:
    """`leg` имеет смысл только для composite-сессии — иначе честная ошибка."""
    _, plan = _persisted_plan(tmp_path)
    index = _find_day(
        plan,
        lambda session, _template: str(session.get("kind") or "single") != "composite",
    )

    with pytest.raises(ValueError, match="leg is only valid for composite sessions"):
        ps.export_workout(plan, index, "fit_csv", leg=1)


def test_export_workout_rejects_session_id_on_sessionless_day(tmp_path) -> None:
    """День без списка сессий не может «содержать» запрошенный session_id."""
    _, plan = _persisted_plan(tmp_path)
    mutated = copy.deepcopy(plan)
    template = mutated["session_templates"][0]
    template["sessions"] = []
    template["session_id"] = "saved-session"

    with pytest.raises(ValueError, match="day has no session_id=requested-session"):
        ps.export_workout(mutated, 0, "fit_csv", session_id="requested-session")


def test_export_workout_returns_activity_tcx(tmp_path) -> None:
    _, plan = _persisted_plan(tmp_path)
    index = _find_day(plan, lambda session, _template: True)

    exported = ps.export_workout(plan, index, "tcx_activity")

    assert exported["filename"].startswith("activity_")
    assert exported["filename"].endswith(".tcx")
    assert exported["mimetype"] == "application/vnd.garmin.tcx+xml"
    assert "<TrainingCenterDatabase" in exported["content"]


def _mutate_checkpoint(db: Database, plan: dict, mutate) -> None:
    """Сохранить снапшот с намеренно битой формой (legacy-совместимость)."""
    checkpoint = build_planning_checkpoint(plan)
    mutate(checkpoint["goal_plan_snapshot"])
    db.save_planning_checkpoint(checkpoint)


def test_week_by_week_reports_data_gap_without_daily_plan(tmp_path) -> None:
    """Снапшот без дневного плана — это gap, а не исключение (ASR-REL-2)."""
    db, plan = _persisted_plan(tmp_path)

    def blank(snapshot: dict) -> None:
        snapshot["daily_plan"] = []
        snapshot["session_templates"] = []
        snapshot["weekly_summary"] = []
        snapshot["weekly_tss_plan"] = []
        snapshot["phases"] = []

    _mutate_checkpoint(db, plan, blank)

    result = ps.week_by_week_plan(db)

    assert result["has_plan"] is True
    assert result["state"] == "data_gap"
    assert result["weeks"] == []
    assert result["reason"]


def test_week_by_week_surfaces_malformed_weekly_rows_from_restore(tmp_path) -> None:
    """Characterization: битую запись недели отсекает уже restore, а не читатель.

    Наблюдение: `restore_goal_plan_from_checkpoint` приводит каждую запись недели
    через `dict(row)`, поэтому не-dict элемент роняет восстановление ValueError-ом
    до `week_by_week_plan`. Значит защитная ветка читателя (пропуск не-dict записей)
    через этот путь недостижима, а «битый checkpoint → data gap» не выполняется.
    Тест фиксирует текущее поведение; менять его — отдельное решение (issue #594).
    """
    db, plan = _persisted_plan(tmp_path)
    _mutate_checkpoint(db, plan, lambda snapshot: snapshot.update(weekly_summary=["мусор"]))

    with pytest.raises(ValueError):
        ps.week_by_week_plan(db)

def test_week_by_week_ignores_malformed_daily_rows(tmp_path) -> None:
    """Битые строки дневного плана не создают фантомных дней и не роняют читатель."""
    db, plan = _persisted_plan(tmp_path)
    baseline = ps.week_by_week_plan(db)

    _mutate_checkpoint(
        db,
        plan,
        lambda snapshot: snapshot.update(
            daily_plan=list(snapshot["daily_plan"]) + ["мусор", [None]]
        ),
    )

    result = ps.week_by_week_plan(db)

    assert result["has_plan"] is True
    assert [week.get("week_start") for week in result["weeks"]] == [
        week.get("week_start") for week in baseline["weeks"]
    ]
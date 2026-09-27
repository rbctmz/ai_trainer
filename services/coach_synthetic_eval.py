"""Синтетический прогон Коуча: сценарий-фикстура и плановый режим (#661).

Проверяет не ответы модели, а доставку данных до неё: маркерный вызов
инструмента (как его эмитит модель) → `collect_tool_results` →
`build_chat_synthesis_prompt`. Ничего сетевого и никакой рабочей базы:
сценарий собирается кодом, провайдер не вызывается.

Зачем отдельный контур. `services/coach_behavioral_eval.py` (#528) проверяет
готовые тексты ответов детерминированными чекерами — то есть «поймал бы гейт
плохой ответ». Здесь проверяется предыдущее звено: попали ли в промпт синтеза
шаги плана, отрезки факта и честные отказы. Ручная проверка 26.09 показала, что
именно это звено ломается незаметно (см. #638: презентер есть, модель его не
видит).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from data.database import Database
from models.ai_coach_runtime import build_chat_synthesis_prompt, collect_tool_results
from models.planning_checkpoints import build_planning_checkpoint
from models.workout_catalog import materialize_session_template


@dataclass(frozen=True)
class SyntheticScenario:
    """Один вопрос с ожиданиями по отрендерированному блоку инструмента."""

    scenario_id: str
    label: str
    question: str
    tool_call: str
    tool_name: str
    must_contain: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyntheticFixtureDays:
    """Даты сценария: смещения от сегодняшнего дня, чтобы фикстура была живой."""

    plan: date
    rest: date
    cached_fact: date
    uncached_fact: date
    brick: date


def synthetic_fixture_days(today: date | None = None) -> SyntheticFixtureDays:
    anchor = today or date.today()
    return SyntheticFixtureDays(
        plan=anchor,
        rest=anchor + timedelta(days=1),
        cached_fact=anchor + timedelta(days=2),
        uncached_fact=anchor + timedelta(days=3),
        brick=anchor + timedelta(days=4),
    )


def _structured_session(day: date) -> dict[str, Any]:
    session = dict(
        materialize_session_template(
            phase="Taper",
            session_role="long",
            sport="bike",
            target_tss=50.0,
            estimated_duration_minutes=60,
            goal_type="Триатлон",
            zone_snapshot={"ftp": 200},
        )
    )
    session.update(
        {
            "date": day.isoformat(),
            "phase": "Taper",
            "sport": "bike",
            "sport_label": "вело",
            "session_focus": "VO2max Intervals",
            "export_name": "Синтетика — VO2max Intervals",
            "session_role": "long",
        }
    )
    return session


def _rest_session(day: date) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "phase": "Taper",
        "sport": "rest",
        "sport_label": "отдых",
        "session_role": "off",
        "session_focus": "Отдых",
        "export_name": "День отдыха",
        "total_tss": 0.0,
        "materialized_steps": [],
    }


def _goal_plan(days: SyntheticFixtureDays) -> dict[str, Any]:
    first_day = days.plan
    start_week = first_day - timedelta(days=first_day.weekday())
    structured = _structured_session(days.plan)
    rest = _rest_session(days.rest)
    return {
        "goal_type": "Триатлон",
        "event_date": (first_day + timedelta(days=8)).isoformat(),
        "events": [
            {"date": (first_day + timedelta(days=8)).isoformat(), "priority": "A", "label": "Синтетический старт"}
        ],
        "weeks_to_race": 2,
        "start_week": start_week,
        "weekly_tss_plan": [300] * 4,
        "base_weekly_tss_plan": [300] * 4,
        "phases": ["Taper"] * 4,
        "daily_plan": [
            (datetime.combine(days.plan, datetime.min.time()), 50, {"bike": 50.0}),
            (datetime.combine(days.rest, datetime.min.time()), 0, {}),
        ],
        "session_templates": [structured, rest],
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


def _provider_cache(intervals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "source": "intervals",
        "analyzed": None,
        "intervals": [dict(row) for row in intervals],
        "groups": [],
    }


BIKE_INTERVALS: tuple[dict[str, Any], ...] = (
    {
        "start_index": 0,
        "moving_time": 660,
        "elapsed_time": 660,
        "average_watts": 128,
        "average_heartrate": 118,
        "max_heartrate": 130,
        "average_cadence": 88,
        "zone": 1,
        "training_load": 4,
        "distance_km": 1.35,
    },
    {
        "start_index": 660,
        "moving_time": 120,
        "elapsed_time": 120,
        "average_watts": 198,
        "average_heartrate": 158,
        "max_heartrate": 166,
        "average_cadence": 94,
        "zone": 4,
        "training_load": 9,
        "distance_km": 0.34,
    },
)

RUN_INTERVALS: tuple[dict[str, Any], ...] = (
    {"start_index": 0, "moving_time": 300, "elapsed_time": 300, "average_heartrate": 130, "distance_km": 0.7},
    {"start_index": 300, "moving_time": 240, "elapsed_time": 240, "average_heartrate": 150, "distance_km": 0.8},
    {"start_index": 540, "moving_time": 180, "elapsed_time": 180, "average_heartrate": 160, "distance_km": 0.6},
)


def _activity(activity_id: str, day: date, sport: str, name: str) -> dict[str, Any]:
    return {
        "activity_id": activity_id,
        "date": day.isoformat(),
        "sport": sport,
        "activity_name": name,
        "duration_minutes": 62.0,
        "distance_km": 32.5,
        "avg_hr": 141,
        "avg_power": 178,
        "tss": 55.0,
    }


def _link_provider(path: str | Path, activity_id: str, provider_id: str) -> None:
    """Связь активности с провайдером: пишем напрямую, публичного API нет."""
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(
            """INSERT INTO activity_provider_links
               (canonical_activity_id, provider, provider_activity_id, match_status)
               VALUES (?, 'intervals', ?, 'matched')""",
            (activity_id, provider_id),
        )
        connection.commit()
    finally:
        connection.close()


def build_synthetic_coach_database(
    path: str | Path,
    days: SyntheticFixtureDays | None = None,
) -> Database:
    """Детерминированная база сценария: план, день отдыха и три активности."""
    days = days or synthetic_fixture_days()
    database = Database(str(path))
    database.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(days)))
    database.save_activities(
        [
            _activity("syn-bike-cached", days.cached_fact, "bike", "Синтетика — вело с кэшем"),
            _activity("syn-run-uncached", days.uncached_fact, "run", "Синтетика — бег без кэша"),
            _activity("syn-brick-bike", days.brick, "bike", "Синтетика — brick вело"),
            _activity("syn-brick-run", days.brick, "run", "Синтетика — brick бег"),
        ]
    )
    database.save_activity_intervals("syn-bike-cached", _provider_cache(BIKE_INTERVALS))
    database.save_activity_intervals("syn-brick-bike", _provider_cache(BIKE_INTERVALS))
    database.save_activity_intervals("syn-brick-run", _provider_cache(RUN_INTERVALS))
    _link_provider(path, "syn-run-uncached", "syn-provider-1")
    return database


def evaluate_scenario(
    ai_tools: Any,
    scenario: SyntheticScenario,
    tool_result_formatter: Callable[[str, Any], str],
) -> dict[str, Any]:
    """Прогнать один сценарий маркерным путём и сверить ожидания."""
    failures: list[str] = []
    _rendered, results = collect_tool_results(
        scenario.tool_call, ai_tools, tool_result_formatter
    )
    if not results:
        return {
            "scenario_id": scenario.scenario_id,
            "passed": False,
            "failures": ["маркер инструмента не распознан: вызов не исполнился"],
        }
    entry = results[0]
    if entry.get("error"):
        failures.append(f"инструмент вернул ошибку: {entry['error']}")
    if entry.get("tool_name") != scenario.tool_name:
        failures.append(
            f"исполнен не тот инструмент: {entry.get('tool_name')!r} вместо {scenario.tool_name!r}"
        )
    block = str(entry.get("formatted_result") or "")
    for fragment in scenario.must_contain:
        if fragment not in block:
            failures.append(f"в блоке нет обязательного фрагмента: {fragment!r}")
    for fragment in scenario.must_not_contain:
        if fragment in block:
            failures.append(f"в блоке есть запрещённый фрагмент: {fragment!r}")
    prompt = build_chat_synthesis_prompt([], scenario.question, results)
    if block.strip() and block.strip() not in prompt:
        failures.append("отрендерированный блок не дошёл до промпта синтеза")
    return {
        "scenario_id": scenario.scenario_id,
        "label": scenario.label,
        "passed": not failures,
        "failures": failures,
    }


def evaluate_scenarios(
    ai_tools: Any,
    scenarios: Iterable[SyntheticScenario],
    tool_result_formatter: Callable[[str, Any], str],
) -> dict[str, Any]:
    """Отчёт по набору сценариев: вердикт, доля прошедших, список падений."""
    results = [
        evaluate_scenario(ai_tools, scenario, tool_result_formatter)
        for scenario in scenarios
    ]
    failed = [result for result in results if not result["passed"]]
    return {
        "verdict": "fail" if failed else "pass",
        "total": len(results),
        "passed": len(results) - len(failed),
        "pass_rate": (len(results) - len(failed)) / len(results) if results else 0.0,
        "failed_scenarios": [result["scenario_id"] for result in failed],
        "results": results,
    }


__all__ = [
    "BIKE_INTERVALS",
    "RUN_INTERVALS",
    "SyntheticFixtureDays",
    "SyntheticScenario",
    "build_synthetic_coach_database",
    "evaluate_scenario",
    "evaluate_scenarios",
    "synthetic_fixture_days",
]

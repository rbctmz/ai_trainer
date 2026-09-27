"""Версионированный реестр синтетических сценариев Коуча (#661).

Каждый сценарий — вопрос, маркерный вызов инструмента (как его эмитит модель) и
ожидания по отрендерированному блоку. Числа в ожиданиях берутся из фикстуры
`services.coach_synthetic_eval`, а не из проекции: иначе проверка сравнивала бы
проекцию саму с собой. Версию поднимать при добавлении, изменении или удалении
сценария, чтобы прогон всегда был привязан к точному набору.
"""
from __future__ import annotations

from services.coach_synthetic_eval import (
    SyntheticFixtureDays,
    SyntheticScenario,
    synthetic_fixture_days,
)

REGISTRY_VERSION = "coach_synthetic_eval_v1"


def build_scenarios(days: SyntheticFixtureDays) -> list[SyntheticScenario]:
    return [
        SyntheticScenario(
            scenario_id="plan-structured-day",
            label="Шаги планового дня доезжают до модели",
            question="Какая структура у тренировки в плановый день?",
            tool_call=f"[TOOL: get_workout_structure, date={days.plan.isoformat()}]",
            tool_name="get_workout_structure",
            must_contain=(
                "Структура тренировки",
                "Синтетика — VO2max Intervals",
                "| 1 |",
                "| 3 |",
                "Вт",
            ),
            must_not_contain=("не материализована", "День отдыха"),
        ),
        SyntheticScenario(
            scenario_id="plan-rest-day",
            label="День отдыха не назван отсутствием структуры",
            question="Что за тренировка в день отдыха?",
            tool_call=f"[TOOL: get_workout_structure, date={days.rest.isoformat()}]",
            tool_name="get_workout_structure",
            must_contain=("День отдыха",),
            must_not_contain=("не материализована",),
        ),
        SyntheticScenario(
            scenario_id="fact-cached-intervals",
            label="Отрезки факта из кэша",
            question="Как прошла велосессия?",
            tool_call=f"[TOOL: get_activity_structure, date={days.cached_fact.isoformat()}]",
            tool_name="get_activity_structure",
            must_contain=(
                "Структура выполненной активности",
                "198 Вт",
                "2:00",
                "отрезков: 2",
                "340 м",
            ),
            must_not_contain=("недоступна",),
        ),
        SyntheticScenario(
            scenario_id="fact-without-cache",
            label="Нет кэша — честное «недоступна» без таблицы отрезков",
            question="Какие отрезки были в беговой сессии?",
            tool_call=(
                f"[TOOL: get_activity_structure, date={days.uncached_fact.isoformat()}, sport=run]"
            ),
            tool_name="get_activity_structure",
            must_contain=("недоступна", "не выгружены"),
            must_not_contain=("| # |", "отрезков:"),
        ),
        SyntheticScenario(
            scenario_id="fact-brick-two-legs",
            label="Brick: две ноги со своими единицами",
            question="Что было на brick-дне?",
            tool_call=f"[TOOL: get_activity_structure, date={days.brick.isoformat()}]",
            tool_name="get_activity_structure",
            must_contain=("вело", "бег", "отрезков: 2", "отрезков: 3"),
            must_not_contain=("недоступна",),
        ),
    ]


SCENARIOS = build_scenarios(synthetic_fixture_days())

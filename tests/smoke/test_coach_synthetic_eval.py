"""Smoke-обвязка синтетического прогона Коуча (#661).

Прогон проверяет доставку данных до модели: маркерный вызов инструмента →
`formatted_result` → промпт синтеза. Сети и ключей провайдера не требуется,
рабочая база не затрагивается — фикстура собирается в `tmp_path`.
"""
from __future__ import annotations

import pytest

from models.ai_tools import AITools
from models.coach_tool_presenter import format_tool_result
from services.coach_synthetic_eval import (
    SyntheticScenario,
    build_synthetic_coach_database,
    evaluate_scenario,
    evaluate_scenarios,
    synthetic_fixture_days,
)
from tests.evals.coach.synthetic_registry import REGISTRY_VERSION, build_scenarios


pytestmark = pytest.mark.smoke


@pytest.fixture()
def synthetic_run(tmp_path):
    days = synthetic_fixture_days()
    database = build_synthetic_coach_database(
        tmp_path / "coach_synthetic.db", days=days
    )
    return AITools(database), build_scenarios(days)


def test_all_synthetic_scenarios_pass(synthetic_run):
    ai_tools, scenarios = synthetic_run

    report = evaluate_scenarios(ai_tools, scenarios, format_tool_result)

    assert report["verdict"] == "pass", report["results"]
    assert report["pass_rate"] == 1.0
    assert report["total"] == 5
    assert report["failed_scenarios"] == []


def test_registry_version_is_stable():
    assert REGISTRY_VERSION == "coach_synthetic_eval_v1"


def test_run_never_touches_the_provider(synthetic_run, monkeypatch):
    """Прогон обязан остаться офлайн: любой заход к провайдеру — падение."""
    import services.activity_intervals as activity_intervals
    import services.intervals_icu as intervals_icu

    calls = []

    def _refuse(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("синтетический прогон не должен ходить к провайдеру")

    monkeypatch.setattr(activity_intervals, "fetch_activity_intervals", _refuse)
    monkeypatch.setattr(activity_intervals, "fetch_stream_structure", _refuse)
    monkeypatch.setattr(intervals_icu, "get_client", _refuse)

    ai_tools, scenarios = synthetic_run
    report = evaluate_scenarios(ai_tools, scenarios, format_tool_result)

    assert report["verdict"] == "pass", report["results"]
    assert calls == []


def test_broken_prompt_delivery_is_caught(synthetic_run, monkeypatch):
    """Самопроверка обвязки: без блока в промпте синтеза прогон падает."""
    import services.coach_synthetic_eval as synthetic_eval

    monkeypatch.setattr(
        synthetic_eval,
        "build_chat_synthesis_prompt",
        lambda *args, **kwargs: "промпт без результатов инструментов",
    )

    ai_tools, scenarios = synthetic_run
    report = evaluate_scenarios(ai_tools, scenarios, format_tool_result)

    assert report["verdict"] == "fail"
    assert set(report["failed_scenarios"]) == {scenario.scenario_id for scenario in scenarios}
    assert all(
        "не дошёл до промпта синтеза" in failure
        for result in report["results"]
        for failure in result["failures"]
    )


def test_wrong_expectation_fails(synthetic_run):
    """Самопроверка чекера: невыполнимое ожидание обязано упасть."""
    ai_tools, _scenarios = synthetic_run
    days = synthetic_fixture_days()
    impossible = SyntheticScenario(
        scenario_id="self-check-impossible",
        label="Заведомо невыполнимое ожидание",
        question="проверка",
        tool_call=f"[TOOL: get_workout_structure, date={days.plan.isoformat()}]",
        tool_name="get_workout_structure",
        must_contain=("этого фрагмента в блоке быть не может",),
    )

    result = evaluate_scenario(ai_tools, impossible, format_tool_result)

    assert result["passed"] is False
    assert any("обязательного фрагмента" in failure for failure in result["failures"])


def test_rest_day_regression_would_be_caught(synthetic_run):
    """Если презентер снова назовёт отдых отсутствием структуры — прогон упадёт."""
    ai_tools, _scenarios = synthetic_run
    days = synthetic_fixture_days()
    regression = SyntheticScenario(
        scenario_id="self-check-rest-wording",
        label="Ожидание старой (неверной) формулировки",
        question="проверка",
        tool_call=f"[TOOL: get_workout_structure, date={days.rest.isoformat()}]",
        tool_name="get_workout_structure",
        must_contain=("не материализована",),
    )

    result = evaluate_scenario(ai_tools, regression, format_tool_result)

    assert result["passed"] is False


def test_uncached_activity_has_no_interval_table(synthetic_run):
    """Отдельная проверка запрета: пустая таблица читалась бы как «отрезков нет»."""
    ai_tools, _scenarios = synthetic_run
    days = synthetic_fixture_days()
    forbidden_table = SyntheticScenario(
        scenario_id="self-check-uncached-table",
        label="Ожидание таблицы там, где данных нет",
        question="проверка",
        tool_call=f"[TOOL: get_activity_structure, date={days.uncached_fact.isoformat()}, sport=run]",
        tool_name="get_activity_structure",
        must_contain=("| # |",),
    )

    result = evaluate_scenario(ai_tools, forbidden_table, format_tool_result)

    assert result["passed"] is False

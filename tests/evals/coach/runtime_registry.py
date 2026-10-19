"""Three narrow, versioned tasks for actual Coach runtime outputs (#528)."""
from tests.planning_fixtures import seed_checkpoint
from dataclasses import dataclass
from datetime import date, timedelta

REGISTRY_VERSION = "coach_runtime_eval_v1"
REPORT_VERSION = "coach_runtime_report_v1"
COMPARISON_REGISTRY_VERSION = "coach_compact_ab_v1"
COMPARISON_REPORT_VERSION = "coach_compact_ab_report_v1"
COMPARISON_FIXTURE_VERSION = "coach_coherent_fixture_v2"
SOURCE_REGISTRY_VERSION = "coach_source_message_ab_v1"
SOURCE_REPORT_VERSION = "coach_source_message_report_v1"
VALIDATION_REGISTRY_VERSION = "coach_cache_conditions_validation_v1"
VALIDATION_REPORT_VERSION = "coach_cache_conditions_report_v1"
VALIDATION_FIXTURE_VERSION = "coach_cache_three_states_v1"
SOURCE_BEFORE_MESSAGE = (
    "Структура недоступна: интервалы этой активности ещё не выгружены в кэш. "
    "Они появятся после синхронизации с Intervals.icu или после открытия "
    "карточки активности; за сетью инструмент не ходит."
)
COMPACT_CONTRACT = {
    "mode": "compact_answer_v1",
    "prompt_suffix": "До 80 слов. Ответь только на заданный вопрос. "
                     "Сохрани существенные факты и ограничения данных.",
}


@dataclass(frozen=True)
class RuntimeScenario:
    """Question and limited response properties, without one correct text."""

    scenario_id: str
    split: str
    target_date: date
    prompt: str
    required_tool: str
    factual_power: tuple[int, ...] = ()
    requires_data_gap: bool = False
    essential_patterns: tuple[str, ...] = ()
    allowed_power: tuple[int, ...] = (128, 198, 178)
    requires_no_fetch_guarantee: bool = False
    requires_rest: bool = False


def build_scenarios(today: date) -> list[RuntimeScenario]:
    """Date anchors are explicit; completed activities are never in the future."""
    plan_day = today - timedelta(days=4)
    fact_day = today - timedelta(days=2)
    missing_day = today - timedelta(days=1)
    return [
        RuntimeScenario(
            "planned-structure", "development", plan_day,
            f"Какая структура плановой велотренировки за {plan_day.isoformat()}? "
            "Коротко: разминка, основная часть, заминка. Отдели план от факта.",
            "get_workout_structure",
        ),
        RuntimeScenario(
            "cached-actual-structure", "development", fact_day,
            f"Какие отрезки были в выполненной велосессии за {fact_day.isoformat()}? "
            "Назови среднюю мощность каждого отрезка в Вт. Коротко, только факт.",
            "get_activity_structure", factual_power=(128, 198),
        ),
        RuntimeScenario(
            "missing-actual-structure", "holdout", missing_day,
            f"Какие отрезки были в выполненной беговой сессии за {missing_day.isoformat()}? "
            "Коротко. Если структуры нет, объясни, чего не хватает; не придумывай отрезки.",
            "get_activity_structure", requires_data_gap=True,
        ),
    ]


def build_comparison_scenarios(today: date) -> list[RuntimeScenario]:
    """Known cases become regression; rest is a new, frozen control case."""
    from dataclasses import replace
    previous = build_scenarios(today)
    return [
        replace(previous[0], split="regression", essential_patterns=(
            r"10\s*[×xх]|\b10\b", r"0:30|30\s*(?:с\b|сек)", r"2:30|2\s*мин\w*\s*30")),
        replace(previous[1], split="regression", allowed_power=(128, 198, 139),
                essential_patterns=(r"11:00|11\s*мин|660\s*(?:с\b|сек)",
                                    r"2:00|2\s*мин|120\s*(?:с\b|сек)")),
        replace(previous[2], split="regression", requires_no_fetch_guarantee=True),
        RuntimeScenario(
            "planned-rest-control", "control", today - timedelta(days=3),
            f"Какая структура плановой сессии за {(today - timedelta(days=3)).isoformat()}? "
            "Это день отдыха или тренировка? Коротко, только по плану.",
            "get_workout_structure", requires_rest=True,
        ),
    ]


def build_source_scenario(today: date) -> RuntimeScenario:
    """Frozen missing-cache regression, no new prompt or response contract."""
    return build_comparison_scenarios(today)[2]


@dataclass(frozen=True)
class CacheValidationCase:
    scenario: RuntimeScenario
    repeat: int
    activity_id: str
    expected_status: str


def build_cache_validation_schedule(today: date) -> list[CacheValidationCase]:
    """Two missing-cache regressions, one structured and one empty control."""
    scenarios = build_comparison_scenarios(today)
    empty_day = today - timedelta(days=3)
    empty = RuntimeScenario(
        "analyzed-empty-actual-structure", "control", empty_day,
        f"Какие отрезки были в выполненной беговой сессии за {empty_day.isoformat()}? "
        "Коротко, только по данным выполненной активности.", "get_activity_structure",
    )
    return [CacheValidationCase(scenarios[2], 1, "syn-run-uncached", "unavailable"),
            CacheValidationCase(scenarios[1], 1, "syn-bike-cached", "structured"),
            CacheValidationCase(empty, 1, "syn-run-empty", "empty"),
            CacheValidationCase(scenarios[2], 2, "syn-run-uncached", "unavailable")]


def cache_validation_metadata(today: date) -> dict:
    """Preflight keeps the full fixed schedule without importing providers."""
    return {"report_version": VALIDATION_REPORT_VERSION,
            "registry_version": VALIDATION_REGISTRY_VERSION,
            "fixture_version": VALIDATION_FIXTURE_VERSION,
            "response_contract": dict(COMPACT_CONTRACT),
            "schedule": [{"scenario_id": case.scenario.scenario_id, "repeat": case.repeat,
                          "expected_activity_id": case.activity_id,
                          "expected_structure_status": case.expected_status,
                          "target_date": case.scenario.target_date.isoformat()}
                         for case in build_cache_validation_schedule(today)]}


def source_report_metadata(after_message: str | None = None) -> dict:
    """Lightweight metadata also available on credential/preflight failure."""
    import hashlib

    def message(text: str | None, provenance: str) -> dict:
        return {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest() if text else None,
                "provenance": provenance}

    return {
        "report_version": SOURCE_REPORT_VERSION, "registry_version": SOURCE_REGISTRY_VERSION,
        "fixture_version": COMPARISON_FIXTURE_VERSION,
        "response_contract": dict(COMPACT_CONTRACT),
        "source_messages": {
            "before": message(SOURCE_BEFORE_MESSAGE,
                              "docs/reports/2026-10-13-coach-compact-ab/live-comparison.json"),
            "after": message(after_message, "models/ai_tools.py::_ACTIVITY_STRUCTURE_MESSAGES[not_fetched]"),
        },
    }


def build_comparison_database(path, today: date):
    """Consistent temporary fixture; all variants clone this exact database."""
    import sqlite3
    from models.planning_checkpoints import build_planning_checkpoint, restore_goal_plan_from_checkpoint
    from services.coach_synthetic_eval import (
        build_synthetic_coach_database, synthetic_fixture_days,
    )

    database = build_synthetic_coach_database(path, synthetic_fixture_days(today - timedelta(days=4)))
    with sqlite3.connect(str(path)) as connection:
        connection.execute(
            "UPDATE activities SET duration_minutes=13, distance_km=1.69, avg_power=139, "
            "avg_hr=124, tss=13 WHERE activity_id='syn-bike-cached'")
        connection.execute(
            "UPDATE activities SET distance_km=10, avg_power=NULL WHERE activity_id='syn-run-uncached'")
        connection.execute("DELETE FROM activities WHERE activity_id IN ('syn-brick-bike','syn-brick-run')")
        connection.execute("DELETE FROM activity_intervals WHERE activity_id IN ('syn-brick-bike','syn-brick-run')")
    plan = restore_goal_plan_from_checkpoint(database.get_latest_planning_checkpoint())
    plan["plan_revision"] = f"{today.isoformat()}T00:00:00"
    plan["session_templates"][0]["export_name"] = "Синтетика — Sprint maintenance"
    plan["session_templates"][0]["session_focus"] = "Sprint maintenance"
    seed_checkpoint(database, build_planning_checkpoint(plan))
    # Database startup fills missing TSS provenance. Complete that once before
    # the canonical snapshot, so opening a clone doesn't change its inputs.
    from data.database import Database
    return Database(str(path))


def build_cache_validation_database(path, today: date):
    """Three coherent actual cache states, normalized once before cloning."""
    from data.database import Database
    from services.coach_synthetic_eval import _activity, _link_provider, _provider_cache
    database = build_comparison_database(path, today)
    day = today - timedelta(days=3)
    activity = _activity("syn-run-empty", day, "run", "Синтетика — анализ без отрезков")
    activity.update(duration_minutes=40, distance_km=6, avg_hr=125, avg_power=None, tss=35)
    database.save_activities([activity])
    cache = _provider_cache([])
    cache["analyzed"] = f"{day.isoformat()}T12:00:00Z"
    database.save_activity_intervals("syn-run-empty", cache)
    _link_provider(path, "syn-run-empty", "syn-provider-empty")
    return Database(str(path))

"""Three narrow, versioned tasks for actual Coach runtime outputs (#528)."""
from dataclasses import dataclass
from datetime import date, timedelta

REGISTRY_VERSION = "coach_runtime_eval_v1"
REPORT_VERSION = "coach_runtime_report_v1"
COMPARISON_REGISTRY_VERSION = "coach_compact_ab_v1"
COMPARISON_REPORT_VERSION = "coach_compact_ab_report_v1"
COMPARISON_FIXTURE_VERSION = "coach_coherent_fixture_v2"
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
    database.save_planning_checkpoint(build_planning_checkpoint(plan))
    # Database startup fills missing TSS provenance. Complete that once before
    # the canonical snapshot, so opening a clone doesn't change its inputs.
    from data.database import Database
    return Database(str(path))

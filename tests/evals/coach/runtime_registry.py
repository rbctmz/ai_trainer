"""Three narrow, versioned tasks for actual Coach runtime outputs (#528)."""
from dataclasses import dataclass
from datetime import date, timedelta

REGISTRY_VERSION = "coach_runtime_eval_v1"
REPORT_VERSION = "coach_runtime_report_v1"


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

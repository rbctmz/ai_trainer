"""Three narrow, versioned tasks for actual Coach runtime outputs (#528)."""
from datetime import date, timedelta

from services.coach_runtime_eval import RuntimeScenario

REGISTRY_VERSION = "coach_runtime_eval_v1"


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

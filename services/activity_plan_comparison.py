"""Local, read-only plan association and activity comparison."""
from typing import Any, Mapping

from models.plan_intervals import planned_intervals_for_match
from models.plan_vs_fact import match_plan_vs_fact


def local_planned_intervals(match: Any, checkpoint: Any, sport: str, lineage: Mapping[str, Any]) -> Any:
    return planned_intervals_for_match(match, checkpoint, activity_sport=sport,
                                       activity_lineage=lineage)


def compare_local_structure(db: Any, planned: Any, actual: list, source: str | None,
                            sport: str) -> Any:
    if planned is None:
        return None
    return match_plan_vs_fact(planned, actual, sport=sport,
                              athlete_profile=db.get_athlete_profile(), actual_source=source)

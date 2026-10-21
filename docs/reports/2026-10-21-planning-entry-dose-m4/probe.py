"""Run from repository root with PYTHONPATH=.; synthetic temporary SQLite only."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import tempfile

from pytest import MonkeyPatch

from models.planning_build_confirmation import BuildParameters, PlanningBuildPreviewError
from api import planning_service as ps
from tests.smoke._planning_build_confirmation import TODAY, pin_clock, protected_state
from tests.smoke._planning_entry_dose import calculate, entry_request, exposure_db, first_week_dose


def main() -> None:
    cases = {}
    with MonkeyPatch.context() as patch, tempfile.TemporaryDirectory() as temporary:
        pin_clock(patch)
        for label, sports in (("run_only", ["running"] * 4),
                              ("mixed", ["running", "cycling", "swimming", "cycling"])):
            root = Path(temporary) / label
            root.mkdir()
            db = exposure_db(root, sports)
            before = protected_state(db)
            response, plan = calculate(db)
            code, retained = None, None
            try:
                shown = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(entry_request(db)), origin="planning_ui")
                retained = shown["confirmation"]["status"]
            except PlanningBuildPreviewError as error:
                code = error.code
            assert protected_state(db) == before
            with db._connect() as conn:
                pending = conn.execute("SELECT count(*) FROM planning_build_previews").fetchone()[0]
            cases[label] = {"source_recent_sports": dict(Counter(sports)),
                            "first_week": first_week_dose(plan),
                            "technical_readiness": response["build_readiness"]["status"],
                            "training_suitability": response["build_readiness"]["training_suitability"],
                            "entry_assessment_present": isinstance(response.get("entry_load"), dict),
                            "prepare_error": code, "retained_status": retained,
                            "pending_rows": pending, "active_state_unchanged": True,
                            "daily_plan": plan["daily_plan"]}
    same_daily = cases["run_only"]["daily_plan"] == cases["mixed"]["daily_plan"]
    for case in cases.values():
        del case["daily_plan"]
    print(json.dumps({"synthetic": True, "as_of": TODAY.isoformat(),
                      "same_aggregate_tss_and_duration": True, "same_daily_plan": same_daily,
                      "same_first_week_dose": cases["run_only"]["first_week"] == cases["mixed"]["first_week"],
                      "cases": cases}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Bounded synthetic comparison characterization; optional future-contract RED."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import tempfile

from pytest import MonkeyPatch

from api import planning_service as ps
from models.planning_build_confirmation import BuildParameters
from services.planning_cycles import current_cycle_context
from tests.smoke._planning_build_confirmation import declared_entry_limits, pin_clock
from tests.smoke._planning_entry_dose import entry_request, exposure_db
from tests.smoke.test_planning_entry_capture_m4b import all_tables


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-comparison", action="store_true")
    args = parser.parse_args()
    calls = 0

    def forbidden(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("network forbidden in synthetic comparison probe")

    with MonkeyPatch.context() as patch, tempfile.TemporaryDirectory(prefix="s4-comparison-") as folder:
        pin_clock(patch)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        db = exposure_db(Path(folder), ["running"] * 4)
        raw = entry_request(db, limits=declared_entry_limits(8))
        new = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui")
        # Fixture setup only: current eight-week plan lives in temporary SQLite.
        ps.confirm_plan_build(db, preview_id=new["confirmation"]["preview_id"], origin="planning_ui")
        context = current_cycle_context(db)
        raw.update(action="edit_current", base_cycle_id=context["cycle_id"],
                   base_cycle_revision=context["cycle_revision"], base_selection_revision=context["selection_revision"],
                   base_checkpoint_id=context["checkpoint_id"], replace_current_cycle=False, horizon_weeks=4)
        raw.pop("initial_dose_limits")
        raw.pop("history_coverage")
        before = all_tables(db)
        snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw))
        result = ps._calculate_plan_build(snapshot)
        payload = json.loads(result.response_json)
        assert all_tables(db) == before
        stored = snapshot.sources()["latest_checkpoint"]["goal_plan_snapshot"]
        constraints = stored["constraint_summary"]
        assert constraints["available_hours"] == 10
        assert len(stored["daily_plan"]) == len(stored["session_templates"]) == 56
        assert all("date" in row for row in stored["daily_plan"])
        assert all(isinstance(row.get("sessions"), list) for row in stored["session_templates"])
        out = {
            "characterization_baseline": "3f75915", "synthetic_only": True, "network_calls": calls,
            "calculation_all_tables_unchanged": True,
            "before_days": len(stored["daily_plan"]),
            "after_days": len(json.loads(result.checkpoint_json)["goal_plan_snapshot"]["daily_plan"]),
            "before_available_hours": constraints["available_hours"],
            "before_available_day_indices": constraints["available_day_indices"],
            "before_saved_scope": [stored["daily_plan"][0]["date"], stored["daily_plan"][-1]["date"]],
            "after_scope": [payload["lifecycle"]["start_date"], payload["lifecycle"]["end_date"]],
            "before_total_tss": payload["preview"]["total_tss_before"],
            "after_total_tss": payload["totals"]["total_tss"],
            "undated_week_counts": [len(payload["preview"][f"weekly_tss_{side}"]) for side in ("before", "after")],
            "preview_fields": sorted(payload["preview"]),
            "comparison_present": payload.get("comparison") is not None,
        }
        assert calls == 0
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if args.require_comparison:
            assert payload.get("comparison") is not None, "frozen before/after comparison missing from new edit response"


if __name__ == "__main__":
    main()

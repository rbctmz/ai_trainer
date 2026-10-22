"""M1 characterization, not a new UI implementation or a comprehension test."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import tempfile

from pytest import MonkeyPatch

from api import planning_service as ps
from api.planning_build_contract import BuildPreviewResponseV2
from models.planning_build_confirmation import BuildParameters
from services.planning_cycles import current_cycle_context
from tests.smoke._planning_build_confirmation import declared_entry_limits, pin_clock
from tests.smoke._planning_entry_dose import entry_request, exposure_db
from tests.smoke.test_planning_entry_capture_m4b import all_tables


def characterize(db, raw: dict) -> tuple[dict, dict]:
    before = all_tables(db)
    frozen = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw))
    calculated = ps._calculate_plan_build(frozen)
    payload = json.loads(calculated.response_json)
    assert all_tables(db) == before, "capture/calculation wrote to synthetic storage"
    shown = ps.prepare_plan_build(
        db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui"
    )
    BuildPreviewResponseV2.model_validate(shown)
    # Separate start_new captures intentionally allocate different cycle IDs.
    # Compare semantic facts, not generated identities or their fingerprints.
    assert shown["totals"] == payload["totals"]
    assert shown["forecast"]["points"] == payload["forecast"]["points"]
    assert shown["lifecycle"]["start_date"] == payload["lifecycle"]["start_date"]
    assert shown["lifecycle"]["end_date"] == payload["lifecycle"]["end_date"]
    after = all_tables(db)
    changed = {table for table in before if before[table] != after[table]}
    assert changed <= {"planning_build_previews", "sqlite_sequence"}, changed
    assert shown["entry_load"]["can_publish"] is True
    assert shown["build_readiness"]["can_confirm"] is True
    points = shown["forecast"]["points"]
    params = shown["parameters"]
    return shown, {
        "action": shown["lifecycle"]["action"],
        "candidate_period": {key: shown["lifecycle"][key] for key in ("start_date", "end_date")},
        "chosen": {key: params[key] for key in ("planning_mode", "intent", "goal_type", "distance", "available_hours", "available_days", "event_date")},
        "applied_events": shown["goal"]["events"],
        "internal_goal_event_date": shown["goal"]["event_date"],
        "actual_totals_tss": shown["totals"],
        "weekly_target_tss": shown["weekly_target"]["target_weekly_tss"],
        "comparison": {key: shown["preview"][key] for key in ("weekly_tss_delta", "total_tss_before", "total_tss_after")},
        "comparison_week_counts": [len(shown["preview"][f"weekly_tss_{side}"]) for side in ("before", "after")],
        "preview_fields": sorted(shown["preview"]),
        "forecast": {"first_point": points[0], "last_point": points[-1], "message": shown["forecast"]["message"]},
        "entry_status": shown["entry_load"]["status"],
        "changed_tables_on_prepare": sorted(changed),
        "calculation_all_tables_unchanged": True,
    }


def main() -> None:
    network_calls = 0

    def forbidden(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("network access forbidden in synthetic M1 probe")

    with MonkeyPatch.context() as patch, tempfile.TemporaryDirectory(prefix="s4-m1-") as directory:
        pin_clock(patch)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        db = exposure_db(Path(directory), ["running"] * 4)
        raw = entry_request(db, limits=declared_entry_limits(8))
        shown, first = characterize(db, raw)
        # Explicit fixture setup only: publish the synthetic eight-week plan,
        # then inspect a four-week edit through the actual current-cycle context.
        ps.confirm_plan_build(db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui")
        current = current_cycle_context(db)
        raw.update(action="edit_current", base_cycle_id=current["cycle_id"],
                   base_cycle_revision=current["cycle_revision"],
                   base_selection_revision=current["selection_revision"],
                   base_checkpoint_id=current["checkpoint_id"], replace_current_cycle=False,
                   horizon_weeks=4)
        raw.pop("initial_dose_limits")
        raw.pop("history_coverage")
        _, edit = characterize(db, raw)
        print(json.dumps({"baseline": "00de15828a17719b96bf8e1dcb213c1aeca55144",
                          "athlete_day": "2026-10-16", "synthetic_only": True,
                          "network_calls": network_calls, "new_8_weeks": first,
                          "edit_4_weeks": edit}, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

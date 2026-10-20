"""Reproduce #677 S3 M1 using pure functions and disposable synthetic SQLite.

Run from any cwd. No personal DB/profile, provider, network or application boot.
Printed values are invented fixtures; this is diagnosis, not a safety validator.
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pytest import MonkeyPatch  # noqa: E402

from data.planning_build_preview_store import get_preview  # noqa: E402
from models.workout_catalog import (  # noqa: E402
    materialize_brick_session, materialize_session_template,
)
from tests.smoke._planning_build_confirmation import (  # noqa: E402
    checkpoint_payload, cycle_fields, parameters, pin_clock, seeded_db,
)
from tests.smoke._planning_cycle_regressions import client_for  # noqa: E402


def main() -> None:
    report = {"fixture": "synthetic-only", "phase_controls": []}
    common = dict(goal_type="triathlon", load_state="balanced", recent_template_keys=())
    for phase in ("Base", "Recovery"):
        for sport in ("bike", "run", "swim"):
            result = materialize_session_template(
                phase=phase, sport=sport, session_role="easy", target_tss=15,
                estimated_duration_minutes=30,
                zone_snapshot={"ftp": 200, "threshold_pace": 300}, **common,
            )
            report["phase_controls"].append({
                "phase": phase, "sport": sport,
                "status": result["materialization_status"],
                "step_count": len(result.get("materialized_steps", [])),
            })
    sprint = materialize_session_template(
        phase="Base", sport="bike", session_role="quality", target_tss=25,
        estimated_duration_minutes=45, zone_snapshot={"ftp": 200}, **common,
    )
    report["sprint"] = {
        "status": sprint["materialization_status"], "failed_bounds": sprint.get("failed_bounds"),
        "requested_tss": sprint["parameter_snapshot"]["requested_tss"],
        "derived_tss": sprint["parameter_snapshot"]["planned_tss"],
        "minutes": sprint["duration_minutes"],
    }
    swim = materialize_session_template(
        phase="Base", sport="swim", session_role="easy", target_tss=15,
        estimated_duration_minutes=30, zone_snapshot={}, **common,
    )
    report["swim"] = {
        "template_key": swim["template_key"], "status": swim["materialization_status"],
        "steps": [{"name": s["name"], "seconds": s["duration_seconds"], "target": s["target"]}
                  for s in swim["materialized_steps"]],
    }
    brick = materialize_brick_session(
        phase="Build", target_tss=90, parts={"bike": 60, "run": 30},
        estimated_duration_minutes=120, goal_type="triathlon",
        zone_snapshot={"ftp": 200, "threshold_pace": 300},
    )
    assert brick["materialization_status"] == "materialized"
    assert brick["duration_minutes"] == sum(x["duration_minutes"] for x in brick["legs"]) + brick["transition_minutes"]
    report["brick_control"] = {
        "minutes": brick["duration_minutes"], "transition_minutes": brick["transition_minutes"],
        "leg_minutes": [x["duration_minutes"] for x in brick["legs"]],
    }
    with MonkeyPatch.context() as patch, tempfile.TemporaryDirectory(prefix="s3-m1-synthetic-") as root:
        pin_clock(patch)
        db = seeded_db(Path(root), rested=True)
        with client_for(db) as client:
            shown = client.post("/api/planning/build", json={
                **parameters(), **cycle_fields(db), "events": [], "available_hours": 10,
            })
            assert shown.status_code == 200, shown.text
            token = shown.json()["confirmation"]["preview_id"]
            row = get_preview(db, token, origin="planning_ui")
            frozen_plan = json.loads(row["checkpoint_json"])["goal_plan_snapshot"]
            applied = client.post("/api/planning/build/confirm", json={"preview_id": token, "confirm": True})
            assert applied.status_code == 200, applied.text
            saved = checkpoint_payload(db)["goal_plan_snapshot"]
            assert saved["session_templates"] == frozen_plan["session_templates"]
            sessions = [s for d in saved["session_templates"] for s in d.get("sessions", [d])
                        if s.get("sport") not in {"rest", "off", None}]
            replay = client.post("/api/planning/build/confirm", json={"preview_id": token, "confirm": True})
            report["http"] = {
                "prepare_status": shown.status_code, "confirm_status": applied.status_code,
                "has_readiness": "build_readiness" in shown.json(),
                "session_statuses": dict(Counter(s.get("materialization_status") for s in sessions)),
                "frozen_prescriptions_preserved": True,
                "replay_status": replay.status_code, "replayed": replay.json()["confirmation"]["replayed"],
            }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

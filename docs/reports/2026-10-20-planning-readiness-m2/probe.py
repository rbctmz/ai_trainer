import json, tempfile, time, collections, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pytest import MonkeyPatch  # noqa: E402
from tests.smoke._planning_build_confirmation import (
    seeded_db,
    parameters,
    cycle_fields,
    pin_clock,
)  # noqa: E402
from tests.smoke._planning_cycle_regressions import client_for  # noqa: E402
from data.planning_build_preview_store import get_preview  # noqa: E402

for horizon, hours in [(8, 4), (8, 6), (8, 10), (16, 10)]:
    with MonkeyPatch.context() as patch, tempfile.TemporaryDirectory() as root:
        pin_clock(patch)
        db = seeded_db(Path(root), rested=True)
        payload = {
            **parameters(),
            **cycle_fields(db),
            "events": [],
            "available_hours": hours,
            "horizon_weeks": horizon,
            "start_date": "2026-10-26",
            "start_week": "2026-10-26",
        }
        if horizon == 16:
            payload.update(
                planning_mode="event_goal",
                events=[
                    {
                        "date": "2027-02-14",
                        "priority": "A",
                        "label": "Synthetic A",
                        "confirmed": True,
                    }
                ],
            )
        with client_for(db) as c:
            start = time.perf_counter()
            res = c.post("/api/planning/build", json=payload)
            elapsed = time.perf_counter() - start
            assert res.status_code == 200, res.text
            row = get_preview(
                db, res.json()["confirmation"]["preview_id"], origin="planning_ui"
            )
            p = json.loads(row["checkpoint_json"])["goal_plan_snapshot"]
            sessions = [
                s for d in p["session_templates"] for s in d.get("sessions", [])
            ]
            weekmins = collections.defaultdict(int)
            for d in p["session_templates"]:
                for s in d.get("sessions", []):
                    weekmins[d["week_index"]] += s.get("duration_minutes", 0)
            print(
                json.dumps(
                    {
                        "requested_weeks": horizon,
                        "actual_weeks": len(p["weekly_summary"]),
                        "hours": hours,
                        "elapsed": round(elapsed, 3),
                        "sessions": len(sessions),
                        "statuses": dict(
                            collections.Counter(
                                s.get("materialization_status") for s in sessions
                            )
                        ),
                        "maximum_week_minutes": max(weekmins.values()),
                        "role_overrides": dict(
                            collections.Counter(
                                s.get("selection_evidence", {}).get("role_override")
                                for s in sessions
                                if s.get("selection_evidence", {}).get("role_override")
                            )
                        ),
                    },
                    ensure_ascii=False,
                )
            )

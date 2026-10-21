"""Synthetic exposure histories for M4 specification; never opens the athlete DB."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import json
from pathlib import Path
from typing import Any, Sequence

from api import planning_service as ps
from data.database import Database
from models.planning_build_confirmation import BuildParameters
from tests.smoke._planning_build_confirmation import (
    TODAY, cycle_fields, parameters, seeded_db,
)


def exposure_db(root: Path, recent_sports: Sequence[str]) -> Database:
    db = seeded_db(root, rested=True)
    with db._connect() as conn:
        conn.execute("DELETE FROM activities")
        for index, ago in enumerate(range(30, 85, 2)):
            conn.execute(
                "INSERT INTO activities(activity_id,date,sport,duration_minutes,tss,tss_method) "
                "VALUES(?,?,?,?,?,?)",
                (f"old-{index}", (TODAY - timedelta(days=ago)).isoformat(),
                 ("running", "cycling", "swimming")[index % 3], 60, 70, "synthetic_fixed"),
            )
        for index, (ago, sport) in enumerate(zip((21, 14, 7, 2), recent_sports, strict=True)):
            conn.execute(
                "INSERT INTO activities(activity_id,date,sport,duration_minutes,tss,tss_method) "
                "VALUES(?,?,?,?,?,?)",
                (f"recent-{index}", (TODAY - timedelta(days=ago)).isoformat(),
                 sport, 45, 55, "synthetic_fixed"),
            )
    return db


def entry_request(db: Database, *, limits: dict[str, Any] | None = None) -> dict[str, Any]:
    values = {
        **parameters(), **cycle_fields(db), "events": [],
        "start_week": "2026-10-26", "start_date": "2026-10-26", "available_hours": 10,
        # Explicit synthetic coverage; omission remains unknown in production.
        "history_coverage": {"status": "user_reported_complete", "start_date": "2026-09-18",
                             "end_date_exclusive": "2026-10-16"},
    }
    if limits is not None:
        values["initial_dose_limits"] = limits
    return values


def calculate(db: Database, *, limits: dict[str, Any] | None = None) -> tuple[dict, dict]:
    snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(entry_request(db, limits=limits)))
    prepared = ps._calculate_plan_build(snapshot)
    return (json.loads(prepared.response_json),
            json.loads(prepared.checkpoint_json)["goal_plan_snapshot"])


def first_week_dose(plan: dict[str, Any]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"minutes": 0, "tss": 0, "sessions": 0})
    for day in plan["session_templates"]:
        if not "2026-10-26" <= day["date"] <= "2026-11-01":
            continue
        for session in day.get("sessions", []):
            leaves = session.get("legs", []) if session.get("kind") == "composite" else [session]
            for leaf in leaves:
                total = totals[leaf["sport"]]
                total["minutes"] += float(leaf.get("duration_minutes") or 0)
                total["tss"] += float((leaf.get("parameter_snapshot") or {}).get("target_tss") or leaf.get("target_tss") or 0)
                total["sessions"] += 1
    return dict(totals)

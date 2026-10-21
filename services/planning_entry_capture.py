"""Connection-bound entry evidence capture; no provider or derived plan reads."""

from __future__ import annotations

import json
from typing import Any, Mapping

from models.planning_checkpoints import restore_goal_plan_from_checkpoint


def capture_entry_inputs(
    conn, frame, latest: Mapping | None, lifecycle: Mapping, parameters: Mapping
) -> dict[str, Any]:
    fields = (
        "activity_id",
        "date",
        "sport",
        "duration_minutes",
        "tss",
        "tss_method",
        "provider_external_id",
        "started_at_utc",
    )
    rows = [{key: raw.get(key) for key in fields} for raw in frame.to_dict("records")]
    identities = {str(r["activity_id"]) for r in rows}
    # The normal bounded activity read cannot date an undated/malformed row.
    # Retain such evidence separately instead of silently certifying coverage.
    invalid = conn.execute(
        "SELECT activity_id,date,sport,duration_minutes,tss,tss_method FROM activities "
        "WHERE date IS NULL OR date(date) IS NULL ORDER BY activity_id LIMIT 501"
    ).fetchall()
    for raw in invalid[:500]:
        item = dict(zip(fields[:6], raw, strict=True))
        if str(item["activity_id"]) not in identities:
            rows.append({**item, "provider_external_id": None, "started_at_utc": None})
    # The entry window stays anchored on edits, even after it ages out of the
    # ordinary 90-day reference capture. Read the 26-day physical window with
    # one extra date at either end for timestamp/timezone boundary conversion.
    cursor = conn.execute(
        "SELECT a.activity_id,a.date,a.sport,a.duration_minutes,a.tss,a.tss_method,"
        "(SELECT CAST(l.external_id AS TEXT) FROM activity_provider_links l WHERE CAST(l.canonical_activity_id AS TEXT)=CAST(a.activity_id AS TEXT) "
        "AND l.provider='intervals' AND l.external_provider='garmin' AND l.external_id IS NOT NULL LIMIT 1),a.started_at_utc "
        "FROM activities a WHERE substr(a.date,1,10) BETWEEN date(?,'-7 days') AND date(?,'+20 days') ORDER BY a.date,a.activity_id LIMIT 5001",
        (lifecycle["start_date"], lifecycle["start_date"]),
    )
    entry_rows = cursor.fetchall()
    for values in entry_rows[:5000]:
        if str(values[0]) not in identities:
            rows.append(dict(zip(fields, values, strict=True)))
    # Retain only links that resolve inside the canonical frame. Foreign remote
    # identifiers are not needed by the frozen public-plan validation evidence.
    canonical_ids = {str(row["activity_id"]) for row in rows}
    for row in rows:
        if str(row.get("provider_external_id") or "") not in canonical_ids:
            row["provider_external_id"] = None
    sports = (
        ["run"]
        if parameters["goal_type"] == "run"
        else ["bike"]
        if parameters["goal_type"] == "bike"
        else ["bike", "run", "swim"]
    )
    owned, versions, retained = {}, [], {}
    if lifecycle["action"] == "edit_current":
        plan = restore_goal_plan_from_checkpoint(dict(latest))
        for day in plan.get("session_templates", []):
            for session in day.get("sessions", []):
                for leaf in [session, *session.get("legs", [])]:
                    if leaf.get("session_id") or leaf.get("leg_id"):
                        owned[str(leaf.get("session_id") or leaf["leg_id"])] = {
                            "date": str(day["date"])[:10],
                            "sport": leaf.get("sport"),
                        }
        versions = [
            r[0]
            for r in conn.execute(
                "SELECT checkpoint_id FROM planning_cycle_versions WHERE cycle_id=? ORDER BY checkpoint_id LIMIT 1001",
                (lifecycle["target_cycle_id"],),
            )
        ]
        old = plan.get("entry_load") or {}
        if (
            parameters.get("history_coverage") is None
            and parameters.get("initial_dose_limits") is None
            and old.get("policy_version") == "entry-load-v1"
            and old.get("scope", {}).get("start_date") == lifecycle["start_date"]
        ):
            retained = {
                sport: old["limits"][sport]
                for sport in sports
                if sport in old.get("limits", {})
            }
    matches = []
    if owned:
        cursor = conn.execute(
            "SELECT p.session_id,p.session_date,p.base_checkpoint_id,p.match_status,p.match_method,p.actual_activity_ids_json "
            "FROM plan_actual_matches p JOIN (SELECT target_key,MAX(revision) AS revision FROM plan_actual_matches GROUP BY target_key) latest "
            "ON p.target_key=latest.target_key AND p.revision=latest.revision "
            "WHERE p.session_date BETWEEN date(?,'-6 days') AND date(?,'+19 days') ORDER BY p.target_key LIMIT 501",
            (lifecycle["start_date"], lifecycle["start_date"]),
        )
        for values in cursor:
            row = dict(
                zip(
                    (
                        "session_id",
                        "session_date",
                        "base_checkpoint_id",
                        "match_status",
                        "match_method",
                        "actual_activity_ids",
                    ),
                    values,
                    strict=True,
                )
            )
            try:
                row["actual_activity_ids"] = json.loads(row["actual_activity_ids"])
                if not isinstance(row["actual_activity_ids"], list) or any(
                    not isinstance(v, str) for v in row["actual_activity_ids"]
                ):
                    raise ValueError("malformed actual identity list")
            except (TypeError, ValueError):
                row.update(actual_activity_ids=[], malformed=True)
            matches.append(row)
    return {
        "rows": rows,
        "target_sports": sports,
        "owned_sessions": owned,
        "owned_checkpoint_ids": versions[:1000],
        "retained_limits": retained or None,
        "matches": matches[:500],
        "truncated": len(entry_rows) > 5000
        or len(invalid) > 500
        or len(matches) > 500
        or len(versions) > 1000,
    }

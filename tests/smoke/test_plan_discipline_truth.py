"""Anchor invariant for Issue #205 (Milestone 1).

The weekly discipline summary an athlete sees must equal, per discipline, the
sum of the sessions the plan would actually export. Today it does not: a day's
blended three-sport load is collapsed onto one dominant sport at materialization
(`build_daily_session_templates` -> `_dominant_sport`), so the executable
calendar drifts away from the weekly table. This test is expected to FAIL until
the multi-session (`day.sessions[]`) distribution work lands, then stay green as
a regression guard.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from data.database import Database
from api import planning_service as ps


pytestmark = pytest.mark.smoke

_DISCIPLINES = ("bike", "run", "swim")


def _session_tss(session: dict) -> float:
    """TSS a single materialized session contributes."""
    if session.get("total_tss") is not None:
        return float(session.get("total_tss") or 0.0)
    steps = session.get("materialized_steps") or session.get("steps") or []
    return round(sum(float(step.get("tss") or 0.0) for step in steps), 1)


def _session_discipline_loads(session: dict):
    """(sport, tss) pairs a single session exports, descending into brick legs."""
    legs = session.get("legs")
    if str(session.get("kind") or "") == "composite" and legs:
        return [(str(leg.get("sport") or ""), float(leg.get("target_tss") or 0.0)) for leg in legs]
    sport = str(session.get("sport") or "")
    if not sport or sport in {"off", "race", "—"}:
        return []
    return [(sport, _session_tss(session))]


def _exported_discipline_loads(template: dict, day_total: float, parts: dict):
    """(sport, tss) pairs a day would actually export.

    Handles both shapes so the invariant is expressed identically before and
    after the fix: the nested ``sessions`` model (each a session, bricks split
    into their bike/run legs), and a legacy day-as-single-session template.
    """
    sessions = template.get("sessions")
    if sessions is not None:
        out = []
        for session in sessions:
            out.extend(_session_discipline_loads(session))
        return out
    legs = template.get("legs")
    if str(template.get("kind") or "") == "composite" and legs:
        return [(str(leg.get("sport") or ""), float(leg.get("target_tss") or 0.0)) for leg in legs]
    sport = str(template.get("sport") or "")
    if not sport or sport in {"off", "race", "—"}:
        return []
    return [(sport, float(day_total or 0.0))]


def test_weekly_discipline_summary_equals_exported_sessions(tmp_path):
    db = Database(str(tmp_path / "discipline-truth.db"))
    event = (datetime.now().date() + timedelta(weeks=12)).isoformat()

    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=10,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )
    active = ps.get_active_plan(db)
    assert active is not None

    weekly_summary = list(active.get("weekly_summary") or [])
    daily_plan = list(active.get("daily_plan") or [])
    templates = list(active.get("session_templates") or [])
    assert weekly_summary and daily_plan and templates

    table = {
        d: round(sum(float(week.get(d, 0.0) or 0.0) for week in weekly_summary), 1)
        for d in _DISCIPLINES
    }

    exported = {d: 0.0 for d in _DISCIPLINES}
    for (dt, day_total, parts), template in zip(daily_plan, templates):
        for sport, tss in _exported_discipline_loads(template, day_total, dict(parts or {})):
            if sport in exported:
                exported[sport] += tss
    exported = {d: round(v, 1) for d, v in exported.items()}

    # No exported session may have a zero-or-negative duration.
    for template in templates:
        for session in template.get("sessions") or []:
            assert int(session.get("duration_minutes") or 0) > 0, session

    # Total load is conserved on both sides; only the per-discipline split is
    # wrong today. This holds before and after the fix and proves the defect is
    # re-labelling onto the dominant sport, not lost data.
    assert round(sum(exported.values()), 1) == pytest.approx(
        round(sum(table.values()), 1), abs=0.1
    ), f"total TSS must be conserved: table={round(sum(table.values()),1)} exported={round(sum(exported.values()),1)}"

    for d in _DISCIPLINES:
        assert exported[d] == pytest.approx(table[d], abs=0.1), (
            f"discipline {d}: weekly table {table[d]} != exported sessions {exported[d]} "
            f"(full table={table}, full exported={exported})"
        )


def test_each_training_day_has_sessions_with_projected_stable_ids(tmp_path):
    """Milestone 2: every training day exposes sessions[] whose primary id equals
    the day id (projection), each session has a unique stable session_id, and
    rest/race days carry no deliverable session."""
    db = Database(str(tmp_path / "session-ids.db"))
    event = (datetime.now().date() + timedelta(weeks=12)).isoformat()
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=10,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )
    active = ps.get_active_plan(db)
    assert active is not None
    daily_plan = list(active.get("daily_plan") or [])
    templates = list(active.get("session_templates") or [])

    seen_ids: set[str] = set()
    training_days = 0
    for (dt, total, parts), template in zip(daily_plan, templates):
        sessions = template.get("sessions")
        assert sessions is not None, template.get("date")
        is_training = (
            float(total or 0.0) > 0
            and str(template.get("session_role") or "") != "off"
            and str(template.get("sport") or "") not in {"off", "race"}
        )
        if is_training:
            training_days += 1
            assert sessions, template.get("date")
            assert template.get("session_id"), template.get("date")
            assert sessions[0].get("session_id") == template.get("session_id")
            for session in sessions:
                sid = str(session.get("session_id") or "")
                assert sid, template.get("date")
                assert sid not in seen_ids, sid
                seen_ids.add(sid)
        else:
            assert sessions == [], template.get("date")
    assert training_days > 0


def test_legacy_template_without_sessions_migrates_on_read():
    """Milestone 2.3: a pre-#205 checkpoint template with no `sessions` key is
    wrapped as sessions=[legacy_session] on read, day scalars preserved."""
    from models.session_identity import ensure_session_identities

    legacy = {
        "date": "2026-07-20",
        "week_index": 0,
        "day_index": 0,
        "phase": "Build",
        "sport": "bike",
        "session_role": "quality",
        "session_focus": "Threshold",
        "duration_minutes": 60,
        "kind": "single",
        "catalog_version": "workout_catalog_v1",
        "template_key": "build:quality:bike",
        "materialized_steps": [
            {"index": 0, "name": "Work", "intensity": "work",
             "duration_seconds": 3600, "tss": 80.0, "target": {"type": "power"}},
        ],
    }
    plan = {
        "daily_plan": [(datetime(2026, 7, 20), 80.0, {"run": 0.0, "bike": 80.0, "swim": 0.0})],
        "session_templates": [dict(legacy)],
    }

    resolved = ensure_session_identities(plan)
    template = resolved["session_templates"][0]

    assert template.get("sessions") is not None
    assert len(template["sessions"]) == 1
    session = template["sessions"][0]
    assert session["sport"] == "bike"
    assert session["session_role"] == "quality"
    assert session["materialized_steps"] == legacy["materialized_steps"]
    assert session["total_tss"] == 80.0
    # day-only keys are not duplicated into the session
    for day_only in ("date", "week_index", "day_index", "phase", "sessions"):
        assert day_only not in session
    # identity is projected onto the primary session
    assert template.get("session_id")
    assert session["session_id"] == template["session_id"]
    # original day fields are preserved unchanged
    assert template["date"] == "2026-07-20"
    assert template["materialized_steps"] == legacy["materialized_steps"]


def test_iter_leaf_sessions_orders_singles_and_splits_brick_legs():
    """Milestone 2.6: the Today/dashboard read model lists every leaf session in
    order, splits a brick into its legs, and yields nothing for rest/race."""
    from models.training_planner import iter_leaf_sessions

    two_single = {
        "sessions": [
            {"kind": "single", "session_id": "a", "sport": "swim",
             "session_role": "recovery", "total_tss": 20.0, "export_name": "Swim"},
            {"kind": "single", "session_id": "b", "sport": "bike",
             "session_role": "easy", "total_tss": 30.0, "export_name": "Bike"},
        ]
    }
    leaves = iter_leaf_sessions(two_single)
    assert [(l["kind"], l["sport"], l["session_id"], l["total_tss"]) for l in leaves] == [
        ("single", "swim", "a", 20.0),
        ("single", "bike", "b", 30.0),
    ]

    brick = {
        "sessions": [
            {"kind": "composite", "session_id": "grp", "export_name": "Brick",
             "session_role": "long", "legs": [
                 {"leg_index": 1, "sport": "bike", "target_tss": 40.0,
                  "leg_id": "grp:1", "template_name": "Bike leg"},
                 {"leg_index": 2, "sport": "run", "target_tss": 20.0,
                  "leg_id": "grp:2", "template_name": "Run leg"},
             ]},
        ]
    }
    legs = iter_leaf_sessions(brick)
    assert [(l["kind"], l["sport"], l["leg_index"], l["group_id"], l["session_id"]) for l in legs] == [
        ("brick_leg", "bike", 1, "grp", "grp:1"),
        ("brick_leg", "run", 2, "grp", "grp:2"),
    ]
    assert [l["total_tss"] for l in legs] == [40.0, 20.0]

    # rest/race days carry no deliverable session, so they yield no leaves
    assert iter_leaf_sessions({"sessions": []}) == []
    assert iter_leaf_sessions({}) == []

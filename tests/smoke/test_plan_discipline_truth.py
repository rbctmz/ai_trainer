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


def _exported_discipline_loads(template: dict, day_total: float, parts: dict):
    """(sport, tss) pairs a day would actually export.

    Handles three shapes so the invariant is expressed identically before and
    after the fix: the target nested ``sessions`` model, today's composite brick
    (``legs``), and today's single collapsed session.
    """
    sessions = template.get("sessions")
    if sessions:
        return [(str(s.get("sport") or ""), _session_tss(s)) for s in sessions]
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

    for d in _DISCIPLINES:
        assert exported[d] == pytest.approx(table[d], abs=0.1), (
            f"discipline {d}: weekly table {table[d]} != exported sessions {exported[d]} "
            f"(full table={table}, full exported={exported})"
        )

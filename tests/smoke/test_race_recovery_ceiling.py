"""RED contract for Issue #237: race-week recovery prescriptions cap the day.

The race-microcycle overlay relabels a day to `recovery` but only applies the
generic pre-race cap (A −7 → ×0.65): a heavy base day stays a 60+ TSS,
100+ minute session wearing a «recovery» label — a semantic oxymoron the
catalog's recovery parameterizations cannot materialize (`legacy_role_fallback`,
found while diagnosing #233). Mirrors the `_ACTIVATION_TSS_CEILING` precedent
from #206 M6: the label must match what the day honestly holds.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from data.database import Database


pytestmark = pytest.mark.smoke

_MONDAY = datetime(2026, 8, 3)  # fixed anchor for the unit-level overlay probe


def test_recovery_ceiling_is_catalog_aligned():
    """The ceiling exists per prescribed sport and never promises more than
    the catalog's recovery variants can hold (TSS bound)."""
    from models.training_planner import _RECOVERY_TSS_CEILING
    from models.workout_catalog import catalog_definitions

    assert set(_RECOVERY_TSS_CEILING) == {"swim", "bike", "run"}
    for sport, ceiling in _RECOVERY_TSS_CEILING.items():
        recovery_defs = [
            definition
            for definition in catalog_definitions()
            if definition.sport == sport and "recovery" in definition.roles
        ]
        assert recovery_defs, sport
        assert 0 < ceiling <= max(d.max_tss for d in recovery_defs), sport


def test_overlay_caps_a_minus_7_recovery_swim_on_a_heavy_day():
    """Unit-level: A-race −7 lands on a heavy swim day → the day is capped to
    the recovery ceiling, not merely ×0.65 of the base load."""
    from models.training_planner import (
        _RECOVERY_TSS_CEILING,
        apply_race_event_overlays,
    )

    daily = []
    for offset in range(14):
        day = _MONDAY + timedelta(days=offset)
        if offset == 6:  # A −7
            daily.append((day, 94.0, {"swim": 94.0, "bike": 0.0, "run": 0.0}))
        elif offset == 13:  # A race day
            daily.append((day, 60.0, {"bike": 60.0, "swim": 0.0, "run": 0.0}))
        else:
            daily.append((day, 50.0, {"bike": 50.0, "swim": 0.0, "run": 0.0}))
    weekly = [
        {
            "week_start": (_MONDAY + timedelta(days=w * 7)).date(),
            "phase": "Race Week" if w else "Taper",
            "weekly_tss": 400,
            "day_roles": ["easy"] * 7,
            "day_focuses": ["—"] * 7,
        }
        for w in range(2)
    ]
    events = [
        {
            "date": (_MONDAY + timedelta(days=13)).date().isoformat(),
            "priority": "A",
            "label": "A",
            "confirmed": True,
        }
    ]

    adjusted, summary, _meta = apply_race_event_overlays(
        daily, weekly, events, goal_type="Триатлон"
    )
    target = adjusted[6]
    assert target[1] <= _RECOVERY_TSS_CEILING["swim"], target
    assert target[2]["swim"] == target[1]
    assert summary[0]["day_roles"][6] == "recovery"


def test_monday_a_race_reference_has_no_unstructured_recovery(tmp_path):
    """The #233 Monday repro end-to-end: with the A race pinned to a Monday,
    the full reference build materializes EVERY session — no
    legacy_role_fallback, no step-less load — and every recovery-role session
    respects its sport ceiling."""
    from api import planning_service as ps
    from models.training_planner import _RECOVERY_TSS_CEILING

    today = datetime.now().date()
    b_date = today + timedelta(days=((2 - today.weekday()) % 7) + 7)  # Wednesday
    a_date = today + timedelta(days=((0 - today.weekday()) % 7) + 77)  # Monday ~12w

    db = Database(str(tmp_path / "recovery-ceiling.db"))
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        events=[
            {"date": b_date.isoformat(), "priority": "B", "label": "B", "confirmed": True},
            {"date": a_date.isoformat(), "priority": "A", "label": "A", "confirmed": True},
        ],
        planning_mode="event_goal",
        available_hours=10,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )
    active = ps.get_active_plan(db)

    offenders = []
    oversized_recovery = []
    for template in active["session_templates"]:
        for session in template.get("sessions") or []:
            status = str(session.get("materialization_status") or "")
            if status == "legacy_role_fallback":
                offenders.append(
                    (template["date"], session.get("sport"), session.get("session_role"), status)
                )
            elif (
                str(session.get("kind") or "single") == "single"
                and float(session.get("total_tss") or 0.0) > 0
                and not (session.get("materialized_steps") or [])
            ):
                offenders.append(
                    (template["date"], session.get("sport"), session.get("session_role"), "no-steps")
                )
            if str(session.get("session_role") or "") == "recovery":
                sport = str(session.get("sport") or "")
                ceiling = _RECOVERY_TSS_CEILING.get(sport)
                if ceiling and float(session.get("total_tss") or 0.0) > ceiling + 0.11:
                    oversized_recovery.append(
                        (template["date"], sport, session.get("total_tss"))
                    )

    assert offenders == [], offenders
    assert oversized_recovery == [], oversized_recovery

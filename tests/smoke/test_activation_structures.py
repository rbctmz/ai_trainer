"""M4 (Issue #205): structured activations, no invalid fallbacks, bookend floor.

Pre-registered RED contract: the `activation` role (introduced by the race
microcycles of #202) must materialize as a real short sharpening session for
bike and run — never `legacy_role_fallback`; a full reference plan carries no
unstructured sessions; and every full-size structure honours the five-minute
warm-up/cool-down floor, with the explicit exception of very short activation
sessions.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from tests.smoke._reference_dates import pinned_reference_events

from data.database import Database


pytestmark = pytest.mark.smoke

_ZONES = {"ftp": 159, "lthr": 160, "threshold_pace": 300}
_BOOKEND_FLOOR_SECONDS = 5 * 60


def _materialize(sport: str, role: str, tss: float, minutes: int, phase: str = "Race Week"):
    from models.training_planner import _estimate_session_duration_minutes
    from models.workout_catalog import materialize_session_template

    seed = minutes or _estimate_session_duration_minutes(tss, sport, role)
    return materialize_session_template(
        phase=phase,
        session_role=role,
        sport=sport,
        target_tss=tss,
        estimated_duration_minutes=seed,
        goal_type="триатлон",
        zone_snapshot=_ZONES,
        load_state="balanced",
        recent_template_keys=[],
    )


@pytest.mark.parametrize(
    ("sport", "tss"),
    [("bike", 37.7), ("bike", 24.7), ("run", 18.4), ("run", 9.7)],
)
def test_activation_materializes_structured_short_sharpening(sport: str, tss: float):
    """The four real fallback cases from the reference plan (D-3/D-1 race
    microcycle days) must become deterministic structured openers."""
    first = _materialize(sport, "activation", tss, 0)
    second = _materialize(sport, "activation", tss, 0)

    assert first == second
    assert first.get("materialization_status") == "materialized", first.get(
        "materialization_status"
    )
    steps = first.get("materialized_steps") or []
    assert steps
    assert sum(int(s.get("duration_seconds") or 0) for s in steps) > 0
    assert sum(float(s.get("tss") or 0.0) for s in steps) == pytest.approx(tss, abs=0.11)
    work_steps = [s for s in steps if s.get("intensity") == "work"]
    assert len(work_steps) >= 2, [s.get("name") for s in steps]
    assert all(int(s.get("duration_seconds") or 0) > 0 for s in steps)


def test_bookend_floor_holds_for_full_structures():
    """A full-size structure (>= 30 min, non-activation) has warm-up and
    cool-down of at least five minutes; the reference plan's 4.5-minute
    cool-downs are the RED case."""
    cases = [
        ("bike", "quality", 80.0, 60),
        ("run", "easy", 25.0, 30),
        ("run", "quality", 50.0, 45),
        ("bike", "easy", 30.0, 45),
        # the v1 legacy pattern path (swim) obeys the same single contract
        ("swim", "recovery", 25.0, 40),
        ("swim", "easy", 35.0, 50),
    ]
    for sport, role, tss, minutes in cases:
        result = _materialize(sport, role, tss, minutes, phase="Build")
        assert result.get("materialization_status") == "materialized", (sport, role)
        steps = result.get("materialized_steps") or []
        total = sum(int(s.get("duration_seconds") or 0) for s in steps)
        if total < 30 * 60:
            continue  # short sessions are outside the full-structure floor
        warm = next((s for s in steps if "warm" in str(s.get("name", "")).lower()), None)
        cool = next((s for s in steps if "cool" in str(s.get("name", "")).lower()), None)
        assert warm and int(warm["duration_seconds"]) >= _BOOKEND_FLOOR_SECONDS, (
            sport, role, warm,
        )
        assert cool and int(cool["duration_seconds"]) >= _BOOKEND_FLOOR_SECONDS, (
            sport, role, cool,
        )


def test_activation_day_load_is_capped_to_definition_ceiling():
    """A capped race-week day with a heavy base must not become a dishonest
    60+ TSS 'short sharpening': the overlay caps an activation day to the
    activation definitions' ceiling (bike 45 / run 35), which always reduces
    and therefore stays inside the #202 overlay contract."""
    from datetime import date as _date, datetime as _datetime, timedelta as _timedelta

    from models.training_planner import apply_race_event_overlays

    start = _date(2026, 7, 20)
    daily = [
        (
            _datetime.combine(start + _timedelta(days=offset), _datetime.min.time()),
            110.0,
            {"run": 0.0, "bike": 110.0, "swim": 0.0},
        )
        for offset in range(14)
    ]
    summaries = [
        {
            "week_start": start + _timedelta(days=week * 7),
            "phase": "Peak",
            "weekly_tss": 770,
            "bike": 770.0,
            "run": 0.0,
            "swim": 0.0,
            "day_roles": ["easy"] * 7,
            "day_focuses": ["—"] * 7,
        }
        for week in range(2)
    ]

    adjusted, _after, _meta = apply_race_event_overlays(
        daily,
        summaries,
        [{"date": "2026-07-30", "priority": "B", "label": "B", "confirmed": True}],
        goal_type="Триатлон",
    )
    by_date = {dt.date().isoformat(): (total, parts) for dt, total, parts in adjusted}
    # B D-3 = bike activation: base 110 capped to 0.60 -> 66, then the
    # activation ceiling brings it to an honest 45
    total, parts = by_date["2026-07-27"]
    assert total == 45.0, (total, parts)
    assert parts["bike"] == 45.0
    # B D-1 = run activation: 110 * 0.25 = 27.5 <= 35 stays as capped
    total_d1, parts_d1 = by_date["2026-07-29"]
    assert total_d1 == 27.5, (total_d1, parts_d1)
    assert parts_d1["run"] == 27.5


def test_reference_plan_has_no_unstructured_sessions(tmp_path):
    """Vertical audit: the full B+A reference plan has zero
    legacy_role_fallback sessions; every leaf carries executable steps."""
    from api import planning_service as ps

    db = Database(str(tmp_path / "m4-audit.db"))
    today = datetime.now().date()
    b_date, a_date = pinned_reference_events(today)
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        events=[
            {"date": b_date.isoformat(), "priority": "B",
             "label": "B", "confirmed": True},
            {"date": a_date.isoformat(), "priority": "A",
             "label": "A", "confirmed": True},
        ],
        planning_mode="event_goal",
        available_hours=10,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )
    active = ps.get_active_plan(db)

    offenders = []
    activation_seen = 0
    for template in active["session_templates"]:
        for session in template.get("sessions") or []:
            status = str(session.get("materialization_status") or "")
            if str(session.get("session_role") or "") == "activation":
                activation_seen += 1
            if status == "legacy_role_fallback":
                offenders.append((template["date"], session.get("sport"),
                                  session.get("session_role"), status))
                continue
            if str(session.get("kind") or "single") == "composite":
                legs = session.get("legs") or []
                if not legs or not all(leg.get("materialized_steps") for leg in legs):
                    offenders.append((template["date"], "brick", "legs-missing-steps", status))
                continue
            if float(session.get("total_tss") or 0.0) > 0 and not (
                session.get("materialized_steps") or []
            ):
                offenders.append((template["date"], session.get("sport"),
                                  session.get("session_role"), status or "no-steps"))

    assert activation_seen >= 2  # the race microcycles are present in the fixture
    assert offenders == [], offenders

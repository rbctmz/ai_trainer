"""Issue #557 M6 acceptance: the data-gap scenario reads back from a real
isolated SQLite database through `GET /api/today` with zero writes.

The scenario is the incident itself: yesterday's sleep and HRV, an RHR row
without a provider measurement date and a current TSB. The morning screen must
report a data gap instead of an actionable Recovery Replan, and evaluating it
must not create checkpoints, proposals, recovery decisions or provider calls.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import pytest

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint

pytestmark = pytest.mark.smoke



def _goal_plan(today: date) -> dict:
    monday = today - timedelta(days=today.weekday())
    daily_plan = []
    templates = []
    for index in range(21):
        session_date = monday + timedelta(days=index)
        is_target = session_date == today
        role = "quality" if is_target else ("off" if index % 7 == 0 else "easy")
        sport = "bike" if is_target else ("off" if role == "off" else "run")
        total_tss = 60.0 if is_target else (0.0 if role == "off" else 20.0)
        parts = {} if role == "off" else {sport: total_tss}
        daily_plan.append(
            (datetime.combine(session_date, datetime.min.time()), total_tss, parts)
        )
        templates.append(
            {
                "date": session_date.isoformat(),
                "week_index": index // 7,
                "day_index": index % 7,
                "phase": "Build",
                "session_role": role,
                "session_focus": "Качество • вело" if is_target else "Лёгкая • бег",
                "sport": sport,
                "sport_label": "вело" if is_target else "бег",
                "duration_minutes": 60 if is_target else 30,
                "export_name": "Quality bike" if is_target else "Easy run",
            }
        )
    weekly_tss = [
        int(sum(row[1] for row in daily_plan[week * 7 : week * 7 + 7])) for week in range(3)
    ]
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "event_date": (today + timedelta(days=70)).isoformat(),
        "weeks_to_race": 10,
        "start_week": monday,
        "weekly_tss_plan": weekly_tss,
        "base_weekly_tss_plan": weekly_tss,
        "phases": ["Build", "Build", "Build"],
        "daily_plan": daily_plan,
        "session_templates": templates,
        "weekly_summary": [
            {
                "week_start": monday + timedelta(days=week * 7),
                "phase": "Build",
                "weekly_tss": weekly_tss[week],
                "capacity_tss": 250,
                "adjustment_note": "—",
            }
            for week in range(3)
        ],
        "constraint_summary": {
            "current_tsb": -18.0,
            "load_state": "fatigued",
            "load_state_label": "Накопленная усталость",
            "notes": [],
        },
        "near_term_edit_version": 0,
        "near_term_edit_rollback_target_checkpoint_id": None,
    }


def _seed_stale_night(db: Database, today: date) -> None:
    """Yesterday's sleep/HRV plus an undated RHR row and a current TSB."""
    yesterday = (today - timedelta(days=1)).isoformat()
    db.sync_sleep_data(
        {yesterday: {"total_sleep_minutes": 360, "sleep_score": 55.0,
                     "sleep_score_observed_at": yesterday}}
    )
    db.sync_hrv_data(
        {yesterday: {"rmssd": 30.0, "rmssd_source": "garmin",
                     "rmssd_observed_at": yesterday}}
    )
    # RHR for the requested date, but without any provider measurement date.
    db.sync_daily_health({today.isoformat(): {"resting_hr": 58, "resting_hr_source": "garmin"}})
    db.save_activities(
        [
            {
                "activity_id": f"acceptance-{offset}",
                "date": (today - timedelta(days=offset)).isoformat(),
                "sport": "running",
                "duration_minutes": 40,
                "distance_km": 7.0,
                "tss": 35.0,
            }
            for offset in range(1, 20)
        ]
    )


def _counts(db_path: str) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "planning_checkpoints",
                "coach_proposals",
                "recovery_decisions",
                "intervals_plan_deliveries",
            )
        }
    finally:
        conn.close()


def test_today_reports_data_gap_without_any_write_or_provider_call(tmp_path, monkeypatch):
    from api.routers.today import today_view

    # `/api/today` anchors readiness on the athlete's current date, so the
    # scenario has to be built around it (mirrors the real morning screen).
    today = datetime.now().date()
    db = Database(str(tmp_path / "acceptance.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    _seed_stale_night(db, today)

    # Any provider access during the evaluation fails loudly.
    import services.intervals_icu as intervals_module

    def _no_provider(*_args, **_kwargs):
        raise AssertionError("provider access is not allowed in the data-gap scenario")

    monkeypatch.setattr(intervals_module, "get_client", _no_provider, raising=False)

    before = _counts(db.db_path)
    payload = today_view(db=db)
    after = _counts(db.db_path)

    # No mutation of planning/proposal/delivery state. The recovery journal is
    # the audit record of this evaluation, so exactly one row is expected there.
    assert after["planning_checkpoints"] == before["planning_checkpoints"]
    assert after["coach_proposals"] == 0
    assert after["intervals_plan_deliveries"] == 0
    assert after["recovery_decisions"] == before["recovery_decisions"] + 1

    # The morning screen reports the gap instead of an actionable card.
    assert payload["gate"]["data_gap"] is True
    assert payload["gate"]["conflicts"] == []
    assert payload["pending_proposal"] is None
    assert payload["proposal"]["relation"] == "none"

    readiness = payload["readiness"]
    assert readiness is not None
    assert readiness["freshness"]["state"] == "data_gap"
    # The derived load state (TSB) is always anchored to today; no *measurement*
    # is confirmed, which is exactly what blocks the intervention.
    assert set(readiness["freshness"]["confirmed_today"]) & {"sleep", "hrv", "resting_hr"} == set()
    assert "resting_hr" in readiness["freshness"]["unverified"]
    assert {"sleep", "hrv"} <= set(readiness["freshness"]["outdated"])
    assert readiness["intervention_score"] is None
    assert (
        readiness["intervention_blocked_reason"]
        == "no_confirmed_today_primary_recovery_measurement"
    )
    # Only the derived load state is eligible; no primary measurement is.
    assert readiness["eligible_inputs"] == ["tsb"]
    assert not set(readiness["eligible_inputs"]) & {"sleep", "hrv", "resting_hr"}
    # The legacy descriptive flag still takes the newest factor date (TSB is
    # anchored to today), which is exactly why the freshness channel exists: it
    # says data_gap while `stale` says False.
    assert readiness["stale"] is False
    # Drivers are the top-3 by contribution, so the per-factor check reads the
    # full factor list; every driver still carries the provenance fields the UI
    # renders as dates.
    factor = next(item for item in readiness["factors"] if item["key"] == "resting_hr")
    assert factor["observation_status"] == "unverified"
    assert factor["observation_as_of"] is None
    assert factor["intervention_eligible"] is False
    assert readiness["drivers"], "the screen must still explain the verdict"
    for driver in readiness["drivers"]:
        assert "observation_status" in driver
        assert "observation_as_of" in driver
        assert "intervention_eligible" in driver


def test_today_confirms_a_freshly_dated_measurement(tmp_path):
    """Control: with a provider-dated primary measurement the gate is open."""
    from api.routers.today import today_view

    today = datetime.now().date()
    db = Database(str(tmp_path / "fresh.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    _seed_stale_night(db, today)
    # Learn the RHR observation date: the same value becomes eligible.
    db.sync_daily_health(
        {
            today.isoformat(): {
                "resting_hr": 58,
                "resting_hr_source": "garmin",
                "resting_hr_observed_at": today.isoformat(),
            }
        }
    )

    readiness = today_view(db=db)["readiness"]

    # TSB is a derived state, so it is always dated to the anchor.
    assert readiness["freshness"]["confirmed_today"] == ["resting_hr", "tsb"]
    assert "resting_hr" in readiness["eligible_inputs"]
    assert readiness["intervention_score"] is not None
    assert readiness["intervention_blocked_reason"] is None
    assert readiness["freshness"]["state"] == "provisional"

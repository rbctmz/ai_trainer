"""Smoke: readiness score must not depend on the training plan (issue #375).

Contract pinned from the IntervalCoach lesson (Readiness Score 2.0, changelog
2026-07-04): "training plan no longer touches the number". The readiness number
answers "how recovered is the body today" and may depend only on body data and
completed activities — never on future planned sessions. ExecPlan:
docs/readiness_plan_purity_execplan.md.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from models.readiness import compute_readiness_today


pytestmark = pytest.mark.smoke

TODAY = date(2026, 7, 9)


def _daily_frame(column: str, values: dict[int, float]) -> pd.DataFrame:
    """Frame with `date` and one value column; keys are day offsets from TODAY."""
    rows = [
        {"date": pd.Timestamp(TODAY - timedelta(days=offset)), column: value}
        for offset, value in sorted(values.items())
    ]
    return pd.DataFrame(rows)


def _history(column: str, value: float, days: int = 28, start_offset: int = 1) -> dict[int, float]:
    return {offset: value for offset in range(start_offset, start_offset + days)}


def _full_inputs(*, activity_tss: float = 40.0) -> dict:
    hrv = _daily_frame("rmssd", {0: 37.0, **_history("rmssd", 37.0)})
    health = _daily_frame("resting_hr", {0: 55.0, **_history("resting_hr", 55.0)})
    sleep = _daily_frame("sleep_score", {0: 80.0})
    training = _daily_frame("training_readiness", {0: 80.0})
    activities = pd.DataFrame(
        [
            {"date": pd.Timestamp(TODAY - timedelta(days=offset)), "tss": activity_tss}
            for offset in range(1, 60)
        ]
    )
    return {
        "sleep_df": sleep,
        "hrv_df": hrv,
        "health_df": health,
        "training_df": training,
        "activities_df": activities,
    }


def _tsb_factor(result: dict) -> dict:
    return next(factor for factor in result["factors"] if factor["key"] == "tsb")


def test_future_planned_sessions_do_not_change_score_or_factors():
    baseline = compute_readiness_today(**_full_inputs(), today=TODAY)
    assert "tsb" in {factor["key"] for factor in baseline["factors"]}

    future_rows = pd.DataFrame(
        [
            {"date": pd.Timestamp(TODAY + timedelta(days=days)), "tss": 200.0}
            for days in (1, 2, 3)
        ]
    )
    inputs = _full_inputs()
    inputs["activities_df"] = pd.concat([inputs["activities_df"], future_rows], ignore_index=True)
    with_plan = compute_readiness_today(**inputs, today=TODAY)

    assert with_plan["score"] == baseline["score"]
    assert _tsb_factor(with_plan)["raw_value"] == _tsb_factor(baseline)["raw_value"]
    assert with_plan["tsb"] == baseline["tsb"]


def test_completed_activity_today_changes_tsb_factor():
    baseline = compute_readiness_today(**_full_inputs(), today=TODAY)

    inputs = _full_inputs()
    inputs["activities_df"] = pd.concat(
        [
            inputs["activities_df"],
            pd.DataFrame([{"date": pd.Timestamp(TODAY), "tss": 180.0}]),
        ],
        ignore_index=True,
    )
    with_done = compute_readiness_today(**inputs, today=TODAY)

    assert _tsb_factor(with_done)["raw_value"] != _tsb_factor(baseline)["raw_value"]


def test_planning_checkpoint_with_future_sessions_does_not_change_snapshot(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot
    from data.database import Database

    db = Database(str(tmp_path / "purity.db"))
    today = datetime.now().strftime("%Y-%m-%d")
    db.sync_sleep_data({today: {"total_sleep_minutes": 480, "sleep_score": 82.0}})
    db.sync_hrv_data({today: {"rmssd": 45.0, "stress_score": 20.0}})
    db.sync_daily_health({today: {"resting_hr": 52, "steps": 8500}})
    db.sync_training_status({today: {"training_status": "PRODUCTIVE", "training_readiness": 78.0}})
    db.save_activities([{"activity_id": "act-1", "date": today, "sport": "running",
                         "duration_minutes": 35, "distance_km": 5.5, "tss": 32.0}])

    before = build_readiness_snapshot(db)
    assert before["score"] is not None

    future_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    db.save_planning_checkpoint(
        {
            "goal_type": "cycling",
            "distance": "100 km",
            "weeks_to_race": 8,
            "session_templates": [
                {
                    "date": future_date,
                    "session_role": "quality",
                    "sport": "bike",
                    "total_tss": 120.0,
                }
            ],
        }
    )

    after = build_readiness_snapshot(db)

    assert after["score"] == before["score"]
    assert after["factors"] == before["factors"]
    assert after["tsb"] == before["tsb"]

"""Smoke: проекция плановых materialized_steps в компактные интервалы (#383).

ExecPlan: docs/plan_vs_fact_execplan.md (Milestone 1). Покрывает чистый
нормализатор ``project_planned_intervals``: классификация work/rest,
длительность, target_zone (структурированный дескриптор), brick legs, fail-closed.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pytest

from data.database import Database
from models.plan_intervals import project_planned_intervals


pytestmark = pytest.mark.smoke


def _step(
    *,
    name: str = "Warm-up",
    intensity: str = "easy",
    duration_seconds: float = 600,
    segment_kind: str = "warmup",
    target_type: str = "power",
    relative_high: float = 0.55,
    relative_low: float = 0.45,
    repeat_index=None,
) -> dict:
    step = {
        "index": 0,
        "name": name,
        "intensity": intensity,
        "duration_seconds": duration_seconds,
        "tss": 10.0,
        "target": {
            "type": target_type,
            "low": 100,
            "high": 130,
            "relative_low": relative_low,
            "relative_high": relative_high,
        },
        "segment_kind": segment_kind,
    }
    if repeat_index is not None:
        step["repeat_index"] = repeat_index
    return step


# --- happy path ------------------------------------------------------------


def test_project_planned_intervals_classifies_work_and_rest():
    session = {
        "materialized_steps": [
            _step(name="Warm-up", intensity="easy", segment_kind="warmup"),
            _step(name="Interval 1", intensity="work", segment_kind="work",
                  duration_seconds=720, relative_high=0.95),
            _step(name="Recovery 1", intensity="easy", segment_kind="recovery",
                  duration_seconds=240, relative_high=0.55),
            _step(name="Cool-down", intensity="easy", segment_kind="cooldown"),
        ]
    }

    intervals = project_planned_intervals(session)

    assert [iv["type"] for iv in intervals] == ["rest", "work", "rest", "rest"]
    assert intervals[0]["segment_kind"] == "warmup"
    assert intervals[1]["duration_seconds"] == 720
    assert intervals[1]["target_zone"]["relative_high"] == round(0.95, 1)
    assert intervals[2]["segment_kind"] == "recovery"
    assert intervals[3]["segment_kind"] == "cooldown"


def test_project_planned_intervals_preserves_order_and_repeat_index():
    session = {
        "materialized_steps": [
            _step(name="Work 1", intensity="work", segment_kind="work",
                  repeat_index=1, relative_high=1.02),
            _step(name="Rest 1", intensity="easy", segment_kind="recovery",
                  repeat_index=1, relative_high=0.6),
            _step(name="Work 2", intensity="work", segment_kind="work",
                  repeat_index=2, relative_high=1.02),
        ]
    }

    intervals = project_planned_intervals(session)

    assert [iv["repeat_index"] for iv in intervals] == [1, 1, 2]
    assert intervals[0]["target_zone"]["relative_high"] == round(1.02, 1)


def test_project_planned_intervals_empty_when_no_steps():
    assert project_planned_intervals({}) == []
    assert project_planned_intervals({"materialized_steps": []}) == []


# --- brick legs ------------------------------------------------------------


def test_project_planned_intervals_flattens_brick_legs_in_order():
    session = {
        "materialized_steps": [],  # composite top-level empty for bricks
        "legs": [
            {"sport": "bike", "materialized_steps": [
                _step(name="Bike work", intensity="work", segment_kind="work"),
            ]},
            {"sport": "run", "materialized_steps": [
                _step(name="Run work", intensity="work", segment_kind="work"),
                _step(name="Run cool", intensity="easy", segment_kind="cooldown"),
            ]},
        ],
    }

    intervals = project_planned_intervals(session)

    assert [iv["name"] for iv in intervals] == ["Bike work", "Run work", "Run cool"]
    assert [iv["type"] for iv in intervals] == ["work", "work", "rest"]


def test_project_planned_intervals_merges_direct_steps_and_legs():
    session = {
        "materialized_steps": [_step(name="Top", intensity="easy")],
        "legs": [{"materialized_steps": [_step(name="Leg", intensity="work")]}],
    }

    intervals = project_planned_intervals(session)

    assert [iv["name"] for iv in intervals] == ["Top", "Leg"]


# --- fail-closed / robustness ---------------------------------------------


def test_project_planned_intervals_fails_closed_on_non_mapping_session():
    with pytest.raises(ValueError):
        project_planned_intervals(["not", "a", "mapping"])


def test_project_planned_intervals_skips_junk_steps_not_raise():
    # Surrounding valid steps survive; junk (non-mapping / non-positive duration)
    # is dropped without raising.
    session = {
        "materialized_steps": [
            _step(name="Work 1", intensity="work"),
            "not-a-mapping",
            {"intensity": "work", "duration_seconds": 0},  # zero duration -> skip
            _step(name="Work 2", intensity="work"),
        ]
    }

    intervals = project_planned_intervals(session)

    assert [iv["name"] for iv in intervals] == ["Work 1", "Work 2"]


def test_project_planned_intervals_handles_missing_target():
    session = {
        "materialized_steps": [
            {"intensity": "work", "duration_seconds": 600, "segment_kind": "work"},
        ]
    }

    intervals = project_planned_intervals(session)

    assert intervals[0]["type"] == "work"
    assert intervals[0]["target_zone"] is None


def test_project_planned_intervals_target_zone_compact_number():
    session = {
        "materialized_steps": [
            _step(relative_high=0.948, relative_low=0.882),
        ]
    }

    intervals = project_planned_intervals(session)

    # _compact_number rounds to 1 decimal; 0.948 -> 0.9.
    assert intervals[0]["target_zone"]["relative_high"] == 0.9
    assert intervals[0]["target_zone"]["relative_low"] == 0.9


def test_project_planned_intervals_work_segment_classifies_as_work():
    # segment_kind="stage" is also a hard effort (race/TT) -> work.
    session = {
        "materialized_steps": [
            {"intensity": "steady", "duration_seconds": 1800, "segment_kind": "stage"},
        ]
    }

    intervals = project_planned_intervals(session)

    assert intervals[0]["type"] == "work"


# --- _planned_snapshot integration (#383 M2) ------------------------------


def test_planned_snapshot_carries_intervals():
    from models.plan_actual_reconciliation import _planned_snapshot

    session = {
        "session_id": "ats_1",
        "sport": "bike",
        "session_role": "key",
        "export_name": "Threshold",
        "total_tss": 80.0,
        "duration_minutes": 60,
        "materialized_steps": [
            _step(name="Work 1", intensity="work", segment_kind="work",
                  duration_seconds=720, relative_high=1.0),
            _step(name="Rest 1", intensity="easy", segment_kind="recovery",
                  duration_seconds=240, relative_high=0.6),
        ],
    }
    template = {"phase": "build", "date": "2026-07-28"}

    snapshot = _planned_snapshot("2026-07-28", session, template, 0)

    assert snapshot["intervals"] == project_planned_intervals(session)
    assert [iv["type"] for iv in snapshot["intervals"]] == ["work", "rest"]


def test_planned_snapshot_intervals_empty_for_unstructured_session():
    from models.plan_actual_reconciliation import _planned_snapshot

    session = {"session_id": "ats_2", "sport": "bike", "total_tss": 40.0,
               "duration_minutes": 60}  # no materialized_steps
    template = {"phase": "base"}

    snapshot = _planned_snapshot("2026-07-28", session, template, 0)

    assert snapshot["intervals"] == []


# --- DB lookup + card field (#383 M2) --------------------------------------


def _seed_plan_actual_match_for_activity(db, activity_id, session_id="ats_1"):
    planned_snapshot = {
        "index": 0,
        "session_id": session_id,
        "date": "2026-07-28",
        "sport": "bike",
        "role": "key",
        "phase": "build",
        "name": "Threshold",
        "tss": 80.0,
        "duration_minutes": 60,
        "parts": {"bike": 80.0},
        "intervals": [
            {"type": "work", "duration_seconds": 720, "target_zone": None,
             "segment_kind": "work", "name": "Work 1"},
        ],
    }
    conn = sqlite3.connect(db.db_path)
    try:
        conn.execute(
            """INSERT INTO plan_actual_matches
               (fingerprint, target_key, revision, session_id, base_checkpoint_id,
                session_date, match_status, match_method, confidence,
                planned_snapshot_json, actual_activity_ids_json, actual_snapshot_json,
                evidence_json, rule_version)
               VALUES (?, ?, 1, ?, 1, '2026-07-28', 'matched', 'auto', 0.9, ?, ?, '{}', '{}', 'v1')""",
            (f"fp-{activity_id}", f"tk-{activity_id}", session_id,
             json.dumps(planned_snapshot), json.dumps([activity_id])),
        )
        conn.commit()
    finally:
        conn.close()


def test_db_get_plan_actual_match_for_activity(tmp_path):

    db = Database(str(tmp_path / "match.db"))
    assert db.get_plan_actual_match_for_activity("act-1") is None
    _seed_plan_actual_match_for_activity(db, "act-1")

    match = db.get_plan_actual_match_for_activity("act-1")

    assert match is not None
    assert match["planned_snapshot"]["intervals"][0]["type"] == "work"
    assert "act-1" in match["actual_activity_ids"]
    # other activity -> None
    assert db.get_plan_actual_match_for_activity("act-other") is None


def test_activity_card_includes_planned_intervals(tmp_path):
    from api.routers import activities as activities_router

    db = Database(str(tmp_path / "api.db"))

    db.save_activities([{
        "activity_id": "act-1", "date": datetime.now().strftime("%Y-%m-%d"),
        "sport": "cycling", "duration_minutes": 60, "distance_km": 30.0,
        "tss": 80.0, "tss_method": "power_tss_v1", "avg_hr": 140, "max_hr": 175,
    }])
    _seed_plan_actual_match_for_activity(db, "act-1")

    card = activities_router.get_activity_card("act-1", db=db)

    planned = card["activity"]["planned_intervals"]
    assert planned is not None
    assert planned[0]["type"] == "work"


def test_activity_card_planned_intervals_null_without_match(tmp_path):
    from api.routers import activities as activities_router

    db = Database(str(tmp_path / "api2.db"))

    db.save_activities([{
        "activity_id": "act-1", "date": datetime.now().strftime("%Y-%m-%d"),
        "sport": "cycling", "duration_minutes": 60, "distance_km": 30.0,
        "tss": 80.0, "tss_method": "power_tss_v1", "avg_hr": 140, "max_hr": 175,
    }])

    card = activities_router.get_activity_card("act-1", db=db)

    assert card["activity"]["planned_intervals"] is None

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
from models.plan_intervals import planned_intervals_for_match, project_planned_intervals


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
    assert intervals[1]["target_zone"]["relative_high"] == 0.95
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
    assert intervals[0]["target_zone"]["relative_high"] == 1.02


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

    assert intervals[0]["target_zone"]["relative_high"] == 0.95
    assert intervals[0]["target_zone"]["relative_low"] == 0.88


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


# --- read-time recovery для legacy snapshot'ов (до #383-M2) -----------------


def _checkpoint_with_session(session_id, date, steps):
    return {
        "goal_plan_snapshot": {
            "session_templates": [
                {
                    "session_id": session_id,
                    "date": date,
                    "materialized_steps": steps,
                }
            ]
        }
    }


def test_planned_intervals_for_match_uses_snapshot_intervals_when_present():
    intervals = [{"type": "work", "duration_seconds": 720}]
    match = {"planned_snapshot": {"session_id": "s-1", "intervals": intervals}}

    assert planned_intervals_for_match(match, {"junk": True}) == intervals


def test_planned_intervals_for_match_recovers_legacy_by_session_id():
    steps = [{"intensity": "work", "segment_kind": "work", "duration_seconds": 720}]
    checkpoint = _checkpoint_with_session("ats_abc", "2026-07-27", steps)
    match = {"planned_snapshot": {"session_id": "ats_abc", "date": "2026-07-27"}}

    result = planned_intervals_for_match(match, checkpoint)

    assert result is not None
    assert result[0]["type"] == "work"
    assert result[0]["duration_seconds"] == 720


def test_planned_intervals_for_match_recovers_legacy_by_date():
    steps = [{"intensity": "work", "segment_kind": "work", "duration_seconds": 405}]
    checkpoint = _checkpoint_with_session("ats_other", "2026-07-27", steps)
    match = {"planned_snapshot": {"session_id": "ats_unknown", "date": "2026-07-27"}}

    result = planned_intervals_for_match(match, checkpoint)

    assert result is not None
    assert result[0]["duration_seconds"] == 405


def test_planned_intervals_for_match_resolves_nested_session_before_date_fallback():
    # P1 (Codex review): on a multi-session day the matched session_id lives in
    # template["sessions"], not on the day template. The date fallback alone
    # would project the day-level steps (999s) instead of the session's (720s).
    checkpoint = {
        "goal_plan_snapshot": {
            "session_templates": [
                {
                    "session_id": "ats_day_level",
                    "date": "2026-07-27",
                    "materialized_steps": [
                        {
                            "intensity": "easy",
                            "segment_kind": "warmup",
                            "duration_seconds": 999,
                        }
                    ],
                    "sessions": [
                        {
                            "session_id": "ats_target",
                            "materialized_steps": [
                                {
                                    "intensity": "work",
                                    "segment_kind": "work",
                                    "duration_seconds": 720,
                                }
                            ],
                        },
                        {
                            "session_id": "ats_other",
                            "materialized_steps": [
                                {
                                    "intensity": "easy",
                                    "segment_kind": "cooldown",
                                    "duration_seconds": 300,
                                }
                            ],
                        },
                    ],
                }
            ]
        }
    }
    match = {"planned_snapshot": {"session_id": "ats_target", "date": "2026-07-27"}}

    result = planned_intervals_for_match(match, checkpoint)

    assert result is not None
    assert result[0]["duration_seconds"] == 720
    assert result[0]["type"] == "work"


def test_planned_intervals_for_match_none_when_unrecoverable():
    assert planned_intervals_for_match(None, {}) is None
    assert (
        planned_intervals_for_match({"planned_snapshot": {"session_id": "x"}}, None)
        is None
    )
    assert (
        planned_intervals_for_match(
            {"planned_snapshot": {}}, {"goal_plan_snapshot": {}}
        )
        is None
    )


def test_activity_card_recovers_legacy_plan_intervals_from_checkpoint(
    tmp_path, monkeypatch
):
    from api.routers import activities as activities_router

    db = Database(str(tmp_path / "legacy-api.db"))
    db.save_activities(
        [
            {
                "activity_id": "act-1",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": 80.0,
                "tss_method": "power_tss_v1",
                "avg_hr": 140,
                "max_hr": 175,
            }
        ]
    )

    # Legacy snapshot: created before #383-M2, no `intervals` key.
    planned_snapshot = {
        "index": 0,
        "session_id": "ats_legacy",
        "date": "2026-07-28",
        "sport": "bike",
        "role": "key",
        "phase": "build",
        "name": "Threshold",
        "tss": 80.0,
        "duration_minutes": 60,
        "parts": {"bike": 80.0},
    }
    conn = sqlite3.connect(db.db_path)
    try:
        conn.execute(
            """INSERT INTO plan_actual_matches
               (fingerprint, target_key, revision, session_id, base_checkpoint_id,
                session_date, match_status, match_method, confidence,
                planned_snapshot_json, actual_activity_ids_json, actual_snapshot_json,
                evidence_json, rule_version)
               VALUES (?, ?, 1, ?, 77, '2026-07-28', 'matched', 'auto', 0.9, ?, ?, '{}', '{}', 'v1')""",
            ("fp-legacy", "tk-legacy", "ats_legacy",
             json.dumps(planned_snapshot), json.dumps(["act-1"])),
        )
        conn.commit()
    finally:
        conn.close()

    checkpoint_data = {
        "goal_plan_snapshot": {
            "session_templates": [
                {
                    "session_id": "ats_legacy",
                    "date": "2026-07-28",
                    "materialized_steps": [
                        {
                            "intensity": "work",
                            "segment_kind": "work",
                            "duration_seconds": 720,
                            "target": {"type": "power", "relative_high": 0.95},
                        },
                        {
                            "intensity": "easy",
                            "segment_kind": "recovery",
                            "duration_seconds": 240,
                            "target": {"type": "power", "relative_high": 0.5},
                        },
                    ],
                }
            ]
        }
    }
    monkeypatch.setattr(db, "get_checkpoint_data", lambda cid: checkpoint_data)
    monkeypatch.setattr(
        activities_router,
        "fetch_activity_intervals",
        lambda db, aid: {
            "analyzed": "2026-08-08T10:00:00Z",
            "intervals": [{"moving_time": 715, "zone": 4}],
            "groups": [],
        },
    )

    card = activities_router.get_activity_card("act-1", db=db)

    planned = card["activity"]["planned_intervals"]
    assert planned is not None
    assert planned[0]["type"] == "work"
    plan_vs_fact = card["activity"]["plan_vs_fact"]
    assert plan_vs_fact is not None
    assert plan_vs_fact["summary"]["planned_work_steps"] == 1
    assert plan_vs_fact["summary"]["matched"] == 1
    assert plan_vs_fact["matches"][0]["matched"] is True

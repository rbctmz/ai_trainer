"""Smoke: матчинг плановых шагов с фактическими интервалами (#383).

ExecPlan: docs/plan_vs_fact_execplan.md (Milestone 3). Покрывает чистую функцию
``match_plan_vs_fact``: матч work-шагов с фактом по порядку + длительности,
отклонения, unmatched, пустые/некорректные входы (fail-open).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from models.plan_vs_fact import match_plan_vs_fact


pytestmark = pytest.mark.smoke


def _planned_work(duration_seconds, relative_high=1.0, **kw):
    step = {
        "type": "work",
        "duration_seconds": duration_seconds,
        "segment_kind": "work",
        "target_zone": {"type": "power", "relative_high": relative_high},
    }
    step.update(kw)
    return step


def _planned_rest(duration_seconds):
    return {"type": "rest", "duration_seconds": duration_seconds, "segment_kind": "recovery"}


def _actual(moving_time, zone=None, **kw):
    iv = {"moving_time": moving_time, "zone": zone}
    iv.update(kw)
    return iv


# --- happy path: exact matches --------------------------------------------


def test_match_three_work_reps_in_order():
    planned = [
        _planned_rest(600),
        _planned_work(720, 0.95),
        _planned_rest(240),
        _planned_work(720, 0.95),
        _planned_rest(240),
        _planned_work(720, 0.95),
        _planned_rest(300),
    ]
    actual = [_actual(715), _actual(722), _actual(718)]

    result = match_plan_vs_fact(planned, actual)

    assert result["summary"] == {"planned_work_steps": 3, "actual_intervals": 3, "matched": 3}
    assert [m["matched"] for m in result["matches"]] == [True, True, True]
    # Small deltas near zero.
    assert abs(result["matches"][0]["duration_delta"]) < 0.05


def test_match_sums_up_in_summary():
    planned = [_planned_work(720), _planned_work(720)]
    actual = [_actual(720), _actual(720)]

    result = match_plan_vs_fact(planned, actual)

    assert result["summary"]["matched"] == 2
    assert result["summary"]["planned_work_steps"] == 2


# --- tolerance + deviation ------------------------------------------------


def test_match_within_30pct_tolerance():
    # planned 720s; actual 900s is +25% (within 30%) -> matched.
    planned = [_planned_work(720)]
    actual = [_actual(900)]

    result = match_plan_vs_fact(planned, actual)

    assert result["matches"][0]["matched"] is True
    assert result["matches"][0]["duration_delta"] == 0.25


def test_match_outside_tolerance_is_unmatched():
    # planned 720s; actual 1100s is +53% (outside 30%) -> unmatched.
    planned = [_planned_work(720)]
    actual = [_actual(1100)]

    result = match_plan_vs_fact(planned, actual)

    assert result["matches"][0]["matched"] is False
    assert result["matches"][0]["actual"] is None
    assert result["summary"]["matched"] == 0


def test_match_carries_zone_for_planned_and_actual():
    planned = [_planned_work(720, relative_high=1.0)]
    actual = [_actual(720, zone=5)]

    result = match_plan_vs_fact(planned, actual)

    assert result["matches"][0]["zone"] == {"planned": 1.0, "actual": 5}


def test_full_projection_and_match_pipeline_preserves_relative_zone_precision():
    from models.plan_intervals import project_planned_intervals

    planned = project_planned_intervals(
        {
            "materialized_steps": [
                {
                    "name": "Threshold",
                    "intensity": "work",
                    "segment_kind": "work",
                    "duration_seconds": 720,
                    "target": {
                        "type": "power",
                        "relative_low": 0.882,
                        "relative_high": 0.95,
                    },
                }
            ]
        }
    )

    result = match_plan_vs_fact(planned, [_actual(720, zone=4)])

    assert result["matches"][0]["planned"]["target_zone"] == {
        "type": "power",
        "low": None,
        "high": None,
        "relative_low": 0.88,
        "relative_high": 0.95,
    }
    assert result["matches"][0]["zone"]["planned"] == 0.95


# --- greedy matching / consumption ---------------------------------------


def test_matched_actual_is_consumed_not_reused():
    # Two identical planned reps, only ONE matching actual -> first matched,
    # second unmatched (greedy consumption, no reuse).
    planned = [_planned_work(720), _planned_work(720)]
    actual = [_actual(720)]

    result = match_plan_vs_fact(planned, actual)

    assert [m["matched"] for m in result["matches"]] == [True, False]
    assert result["summary"]["matched"] == 1


def test_non_matching_actual_is_skipped_to_find_a_match():
    # A short recovery interval sits between; matcher skips it to the matching one.
    planned = [_planned_work(720)]
    actual = [_actual(60), _actual(718)]

    result = match_plan_vs_fact(planned, actual)

    assert result["matches"][0]["matched"] is True
    assert result["matches"][0]["actual"]["moving_time"] == 718


def test_matching_never_moves_backwards_in_actual_order():
    planned = [_planned_work(60), _planned_work(300)]
    actual = [_actual(300), _actual(60)]

    result = match_plan_vs_fact(planned, actual)

    assert [match["matched"] for match in result["matches"]] == [True, False]
    assert result["summary"]["matched"] == 1


# --- fail-open on bad/empty inputs ----------------------------------------


def test_match_no_work_steps_returns_empty():
    planned = [_planned_rest(600), _planned_rest(300)]
    actual = [_actual(600)]

    result = match_plan_vs_fact(planned, actual)

    assert result["matches"] == []
    assert result["summary"] == {"planned_work_steps": 0, "actual_intervals": 1, "matched": 0}


def test_match_non_list_inputs_fail_open():
    assert match_plan_vs_fact(None, None) == {
        "matches": [],
        "summary": {"planned_work_steps": 0, "actual_intervals": 0, "matched": 0},
    }
    assert match_plan_vs_fact({"not": "list"}, [_actual(600)])["matches"] == []


def test_match_empty_lists():
    result = match_plan_vs_fact([], [])

    assert result["matches"] == []
    assert result["summary"]["planned_work_steps"] == 0


def test_match_falls_back_to_elapsed_time_when_no_moving_time():
    planned = [_planned_work(720)]
    actual = [{"elapsed_time": 725}]  # no moving_time

    result = match_plan_vs_fact(planned, actual)

    assert result["matches"][0]["matched"] is True


# --- #398: флаг «план перепланирован после доставки» -------------------------


def test_plan_replanned_after_delivery_flags_earlier_delivery():
    from models.plan_vs_fact import plan_replanned_after_delivery

    match = {"session_date": "2026-08-08", "base_checkpoint_id": 77}
    checkpoint = {"checkpoint_source": "recovery_replan"}
    deliveries = [
        {
            "checkpoint_id": 76,
            "dates": ["2026-08-08"],
            "created_at": "2026-08-08T06:41:10",
        },
        {
            "checkpoint_id": 78,
            "dates": ["2026-08-10"],
            "created_at": "2026-08-08T06:41:26",
        },
    ]

    result = plan_replanned_after_delivery(match, checkpoint, deliveries)

    assert result == {
        "reason": "replanned_after_delivery",
        "delivered_at": "2026-08-08T06:41:10",
        "delivery_checkpoint_id": 76,
        "replanned_checkpoint_id": 77,
    }


def test_plan_replanned_after_delivery_none_without_replan():
    from models.plan_vs_fact import plan_replanned_after_delivery

    assert (
        plan_replanned_after_delivery(
            {"session_date": "2026-08-08", "base_checkpoint_id": 77},
            {"checkpoint_source": "initial_plan"},
            [{"checkpoint_id": 76, "dates": ["2026-08-08"], "created_at": "x"}],
        )
        is None
    )


def test_plan_replanned_after_delivery_none_without_earlier_delivery():
    from models.plan_vs_fact import plan_replanned_after_delivery

    match = {"session_date": "2026-08-08", "base_checkpoint_id": 77}
    checkpoint = {"checkpoint_source": "recovery_replan"}

    assert plan_replanned_after_delivery(match, checkpoint, []) is None
    # Доставка из того же/более нового чекпоинта не считается «ранней версией».
    assert (
        plan_replanned_after_delivery(
            match,
            checkpoint,
            [{"checkpoint_id": 78, "dates": ["2026-08-08"], "created_at": "x"}],
        )
        is None
    )


def test_activity_card_plan_replanned_after_delivery_flag(tmp_path, monkeypatch):
    import json as _json
    import sqlite3

    from api.routers import activities as activities_router
    from data.database import Database

    db = Database(str(tmp_path / "replan.db"))
    _seed_activity(db)
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(db.db_path)
    try:
        conn.execute(
            """INSERT INTO planning_checkpoints
               (id, goal_type, distance, weeks_to_race, checkpoint_data, created_at)
               VALUES (76, 'triathlon', 'olympic', 8, ?, '2026-08-08T05:00:00')""",
            (_json.dumps({"checkpoint_source": "initial_plan", "goal_plan_snapshot": {}}),),
        )
        conn.execute(
            """INSERT INTO planning_checkpoints
               (id, goal_type, distance, weeks_to_race, checkpoint_data, created_at)
               VALUES (77, 'triathlon', 'olympic', 8, ?, ?)""",
            (
                _json.dumps({"checkpoint_source": "recovery_replan", "goal_plan_snapshot": {}}),
                f"{today}T06:41:49",
            ),
        )
        conn.execute(
            """INSERT INTO coach_proposals
               (date, action, status, params_json, preview_json, result_json, created_at)
               VALUES (?, 'recovery_replan', 'approved', '{}', '{}', ?, '2026-08-08T06:41:10')""",
            (
                today,
                _json.dumps(
                    {
                        "delivery": {
                            "status": "success",
                            "checkpoint_id": 76,
                            "dates": [today],
                        }
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    _seed_plan_match(db, base_checkpoint_id=77)
    monkeypatch.setattr(
        activities_router, "fetch_activity_intervals", lambda db, aid: None
    )

    card = activities_router.get_activity_card("act-1", db=db)

    risk = card["activity"]["plan_vs_fact"]["plan_replanned_after_delivery"]
    assert risk is not None
    assert risk["reason"] == "replanned_after_delivery"
    assert risk["delivery_checkpoint_id"] == 76
    assert risk["replanned_checkpoint_id"] == 77


# --- API: карточка несёт план vs факт --------------------------------------


def _seed_activity(db, activity_id: str = "act-1") -> None:
    db.save_activities(
        [
            {
                "activity_id": activity_id,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": 60.0,
                "tss_method": "power_tss_v1",
                "avg_hr": 140,
                "max_hr": 175,
            }
        ]
    )


def _seed_plan_match(db, activity_id: str = "act-1", base_checkpoint_id: int = 1) -> None:
    db.save_plan_actual_match(
        {
            "fingerprint": "fp-plan-vs-fact",
            "target_key": "tk-1",
            "base_checkpoint_id": base_checkpoint_id,
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "match_status": "matched",
            "match_method": "date_sport_heuristic",
            "confidence": 1.0,
            "planned_snapshot": {
                "session_id": "s-1",
                "intervals": [
                    {
                        "type": "work",
                        "duration_seconds": 720,
                        "target_zone": 1.0,
                        "segment_kind": "work",
                        "repeat_index": 0,
                    },
                    {
                        "type": "rest",
                        "duration_seconds": 240,
                        "target_zone": None,
                        "segment_kind": "recovery",
                        "repeat_index": 0,
                    },
                    {
                        "type": "work",
                        "duration_seconds": 720,
                        "target_zone": 1.0,
                        "segment_kind": "work",
                        "repeat_index": 1,
                    },
                ],
            },
            "actual_activity_ids": [activity_id],
            "actual_snapshot": {"tss": 60.0, "duration_minutes": 60},
            "evidence": {},
            "rule_version": "test",
        }
    )


def test_activity_card_plan_vs_fact_contract(tmp_path, monkeypatch):
    from api.routers import activities as activities_router
    from data.database import Database

    db = Database(str(tmp_path / "plan-vs-fact-api.db"))
    _seed_activity(db)
    _seed_plan_match(db)
    monkeypatch.setattr(
        activities_router,
        "fetch_activity_intervals",
        lambda db, aid: {
            "analyzed": "2026-08-08T10:00:00Z",
            "intervals": [_actual(715), _actual(722), _actual(718)],
            "groups": [],
        },
    )

    card = activities_router.get_activity_card("act-1", db=db)

    assert card["activity"]["planned_intervals"][0]["type"] == "work"
    plan_vs_fact = card["activity"]["plan_vs_fact"]
    assert plan_vs_fact is not None
    assert plan_vs_fact["summary"] == {
        "planned_work_steps": 2,
        "actual_intervals": 3,
        "matched": 2,
    }
    assert [match["matched"] for match in plan_vs_fact["matches"]] == [True, True]
    assert plan_vs_fact["matches"][0]["actual"]["moving_time"] == 715


def test_activity_card_plan_vs_fact_null_without_plan(tmp_path, monkeypatch):
    from api.routers import activities as activities_router
    from data.database import Database

    db = Database(str(tmp_path / "plan-vs-fact-noplan.db"))
    _seed_activity(db)
    monkeypatch.setattr(
        activities_router, "fetch_activity_intervals", lambda db, aid: None
    )

    card = activities_router.get_activity_card("act-1", db=db)

    assert card["activity"]["planned_intervals"] is None
    assert card["activity"]["plan_vs_fact"] is None

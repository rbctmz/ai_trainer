"""Smoke: матчинг плановых шагов с фактическими интервалами (#383).

ExecPlan: docs/plan_vs_fact_execplan.md (Milestone 3). Покрывает чистую функцию
``match_plan_vs_fact``: матч work-шагов с фактом по порядку + длительности,
отклонения, unmatched, пустые/некорректные входы (fail-open).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

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

    assert result["summary"] == {
        "planned_steps": 7,
        "planned_work_steps": 3,
        "actual_intervals": 3,
        "matched_steps": 3,
        "matched": 3,
    }
    assert result["alignment_mode"] == "work_intervals"
    assert result["step_matches"] == []
    assert [m["matched"] for m in result["matches"]] == [True, True, True]
    # Small deltas near zero.
    assert abs(result["matches"][0]["duration_delta"]) < 0.05


def test_match_sums_up_in_summary():
    planned = [_planned_work(720), _planned_work(720)]
    actual = [_actual(720), _actual(720)]

    result = match_plan_vs_fact(planned, actual)

    assert result["summary"]["matched"] == 2
    assert result["summary"]["planned_work_steps"] == 2


def test_contiguous_timeline_groups_auto_laps_into_planned_steps():
    planned = [
        {**_planned_rest(315), "segment_kind": "warmup", "name": "Warm-up"},
        _planned_work(1155, 0.8, segment_kind="stage", name="Aerobic endurance"),
        _planned_work(315, 0.88, segment_kind="stage", name="Steady finish"),
        {**_planned_rest(315), "segment_kind": "cooldown", "name": "Cool-down"},
    ]
    durations = [316, 465, 453, 237, 315, 321]
    zones = [2, 2, 2, 2, 3, 2]
    actual = []
    cursor = 0
    for duration, zone in zip(durations, zones):
        actual.append(
            _actual(
                duration,
                zone=zone,
                start_index=cursor,
                average_watts=280 + zone * 5,
            )
        )
        cursor += duration

    result = match_plan_vs_fact(planned, actual)

    assert result["alignment_mode"] == "timeline"
    assert result["summary"] == {
        "planned_steps": 4,
        "planned_work_steps": 2,
        "actual_intervals": 6,
        "matched_steps": 4,
        "matched": 2,
        "intensity_assessed": 0,
        "intensity_within": 0,
    }
    assert [item["matched"] for item in result["step_matches"]] == [
        True,
        True,
        True,
        True,
    ]
    assert result["step_matches"][1]["actual"]["moving_time"] == 1155
    assert result["step_matches"][1]["actual"]["source_interval_count"] == 3
    assert result["step_matches"][1]["zone"]["actual"] == 2
    assert result["step_matches"][1]["duration_delta"] == 0
    assert result["step_matches"][2]["actual"]["source_interval_count"] == 1
    assert [item["matched"] for item in result["matches"]] == [True, True]


def test_timeline_compares_run_pace_to_threshold_in_same_scale():
    planned = [
        {
            **_planned_rest(315),
            "segment_kind": "warmup",
            "name": "Warm-up",
            "target_zone": {
                "type": "pace",
                "relative_low": 0.57,
                "relative_high": 0.73,
            },
        },
        _planned_work(
            1155,
            0.8,
            segment_kind="stage",
            name="Aerobic endurance",
            target_zone={
                "type": "pace",
                "relative_low": 0.64,
                "relative_high": 0.8,
            },
        ),
        _planned_work(
            315,
            0.88,
            segment_kind="stage",
            name="Steady finish",
            target_zone={
                "type": "pace",
                "relative_low": 0.72,
                "relative_high": 0.88,
            },
        ),
        {
            **_planned_rest(315),
            "segment_kind": "cooldown",
            "name": "Cool-down",
            "target_zone": {
                "type": "pace",
                "relative_low": 0.52,
                "relative_high": 0.68,
            },
        },
    ]
    durations = [316, 465, 453, 237, 315, 321]
    distances = [0.65, 1.0, 1.0, 0.51, 0.73, 0.62]
    heart_rates = [117, 134, 137, 139, 143, 136]
    actual = []
    cursor = 0
    for duration, distance, heart_rate in zip(durations, distances, heart_rates):
        actual.append(
            _actual(
                duration,
                start_index=cursor,
                distance_km=distance,
                average_heartrate=heart_rate,
                zone=2,
            )
        )
        cursor += duration

    result = match_plan_vs_fact(
        planned,
        actual,
        sport="running",
        athlete_profile={"threshold_pace_seconds_per_km": 340},
    )

    matches = result["step_matches"]
    assert [item["intensity"]["status"] for item in matches] == [
        "within",
        "within",
        "within",
        "within",
    ]
    assert [item["intensity"]["actual_relative"] for item in matches] == [
        0.7,
        0.74,
        0.79,
        0.66,
    ]
    assert matches[1]["actual"]["source_interval_durations"] == [465, 453, 237]
    assert matches[1]["intensity"]["actual_value"] == pytest.approx(460.2, abs=0.1)
    assert matches[1]["intensity"]["unit"] == "seconds_per_km"
    assert matches[1]["intensity"]["average_heartrate"] == 136


def test_intensity_is_unavailable_without_matching_threshold():
    planned = [
        _planned_work(
            300,
            target_zone={
                "type": "pace",
                "relative_low": 0.8,
                "relative_high": 0.9,
            },
        )
    ]
    actual = [_actual(300, start_index=0, distance_km=1.0)]

    result = match_plan_vs_fact(planned, actual, sport="running")

    assert result["step_matches"][0]["intensity"]["status"] == "unavailable"
    assert result["step_matches"][0]["intensity"]["actual_relative"] is None


@pytest.mark.parametrize(
    ("sport", "target", "profile", "actual", "relative", "unit", "status"),
    [
        (
            "bike",
            {"type": "power", "relative_low": 0.8, "relative_high": 0.9},
            {"ftp": 200},
            {"average_watts": 180},
            0.9,
            "watts",
            "within",
        ),
        (
            "run",
            {"type": "heart_rate", "relative_low": 0.75, "relative_high": 0.85},
            {"lthr": 180},
            {"average_heartrate": 144},
            0.8,
            "bpm",
            "within",
        ),
        (
            "swim",
            {"type": "pace", "relative_low": 0.8, "relative_high": 0.9},
            {"swim_threshold_pace_seconds_per_100m": 60},
            {"distance_km": 1.0},
            0.86,
            "seconds_per_100m",
            "within",
        ),
        (
            "bike",
            {"type": "power", "relative_low": 0.8, "relative_high": 0.9},
            {"ftp": 200},
            {"average_watts": 210},
            1.05,
            "watts",
            "above",
        ),
    ],
)
def test_intensity_uses_metric_selected_by_plan(
    sport, target, profile, actual, relative, unit, status
):
    planned = [_planned_work(700, target_zone=target)]
    intervals = [_actual(700, start_index=0, **actual)]

    result = match_plan_vs_fact(
        planned,
        intervals,
        sport=sport,
        athlete_profile=profile,
    )

    intensity = result["step_matches"][0]["intensity"]
    assert intensity["actual_relative"] == relative
    assert intensity["unit"] == unit
    assert intensity["status"] == status


def test_timeline_alignment_does_not_accept_large_duration_deviation():
    planned = [_planned_work(720)]
    actual = [_actual(1100, start_index=0)]

    result = match_plan_vs_fact(planned, actual)

    assert result["alignment_mode"] == "timeline"
    assert result["step_matches"][0]["matched"] is False
    assert result["step_matches"][0]["actual"]["moving_time"] == 1100
    assert result["summary"]["matched_steps"] == 0


def test_timeline_with_gap_keeps_conservative_work_interval_matching():
    planned = [_planned_work(720)]
    actual = [
        _actual(60, start_index=0),
        _actual(718, start_index=120),
    ]

    result = match_plan_vs_fact(planned, actual)

    assert result["alignment_mode"] == "work_intervals"
    assert result["step_matches"] == []
    assert result["matches"][0]["actual"]["moving_time"] == 718


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
    assert result["summary"] == {
        "planned_steps": 2,
        "planned_work_steps": 0,
        "actual_intervals": 1,
        "matched_steps": 0,
        "matched": 0,
    }


def test_match_non_list_inputs_fail_open():
    assert match_plan_vs_fact(None, None) == {
        "alignment_mode": "work_intervals",
        "step_matches": [],
        "matches": [],
        "summary": {
            "planned_steps": 0,
            "planned_work_steps": 0,
            "actual_intervals": 0,
            "matched_steps": 0,
            "matched": 0,
        },
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
        "planned_steps": 3,
        "planned_work_steps": 2,
        "actual_intervals": 3,
        "matched_steps": 2,
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


def test_activity_card_passes_sport_and_profile_to_intensity_matcher(
    tmp_path, monkeypatch
):
    from api.routers import activities as activities_router
    from data.database import Database

    db = Database(str(tmp_path / "plan-vs-fact-intensity.db"))
    _seed_activity(db)
    _seed_plan_match(db)
    db.save_athlete_profile(
        {"ftp": 200, "weight_kg": 75, "lthr": 160, "source": "test"}
    )
    monkeypatch.setattr(
        activities_router,
        "fetch_activity_intervals",
        lambda db, aid: {"intervals": [_actual(720)], "groups": []},
    )
    captured = {}

    def fake_match(planned, actual, **context):
        captured.update(context)
        return {"matches": [], "step_matches": [], "summary": {}}

    monkeypatch.setattr(activities_router, "match_plan_vs_fact", fake_match)

    activities_router.get_activity_card("act-1", db=db)

    assert captured["sport"] == "bike"
    assert captured["athlete_profile"]["ftp"] == 200


def test_activity_card_timeline_alignment_ui_contract() -> None:
    page = Path("web/app/activities/page.tsx").read_text(encoding="utf-8")
    types = Path("web/lib/types.ts").read_text(encoding="utf-8")

    assert "step_matches: PlanVsFactMatch[]" in types
    assert "source_interval_count?: number" in types
    assert 'alignment_mode: "timeline" | "work_intervals"' in types
    assert "Этапы по длительности" in page
    assert "Плановая цель" in page
    assert "Фактическая интенсивность" in page
    assert "Высота: интенсивность относительно порога" in page
    assert "planVsFact.step_matches" in page
    assert "matchedFactStripSegments" in page
    assert "divisionsPct" in page
    assert "sourceDivisions(actual, index > 0)" in page
    assert "border-ink/40" in Path(
        "web/components/WorkoutStrip.tsx"
    ).read_text(encoding="utf-8")

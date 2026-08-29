"""Behavior contract for Issue D: pre-registered session-quality shadow forecasts."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, datetime, timedelta
import sqlite3
from threading import Barrier

import pytest
import pandas as pd

from data.data_processor import ActivityProcessor
from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from models.session_quality_forecast import (
    RULE_VERSION,
    brier_score,
    build_session_quality_forecast,
    classify_plan_adherence,
)
from tests.sync_fixtures import legacy_upsert_activities


pytestmark = pytest.mark.smoke


def _readiness(score: float = 75.0, confidence: float = 0.8) -> dict:
    return {
        "score": score,
        "status": "ready" if score >= 60 else "low",
        "confidence": confidence,
        "drivers": [{"key": "hrv", "evidence": "HRV -8% к базе"}],
        "source": "canonical_snapshot",
    }


def _planned(
    *,
    role: str = "quality",
    sport: str = "bike",
    tss: float = 60.0,
    duration: int = 60,
    target_date: str = "2026-07-14",
    index: int = 8,
) -> dict:
    return {
        "date": target_date,
        "index": index,
        "role": role,
        "sport": sport,
        "tss": tss,
        "duration_minutes": duration,
        "name": "Качество • вело" if role == "quality" else "Длительная • вело",
    }


def _goal_plan(today: date, *, days_until: int = 2, role: str = "quality") -> dict:
    monday = today - timedelta(days=today.weekday())
    target_date = today + timedelta(days=days_until)
    daily_plan = []
    templates = []
    for index in range(14):
        session_date = monday + timedelta(days=index)
        is_target = session_date == target_date
        session_role = role if is_target else ("off" if index % 7 == 0 else "easy")
        sport = "bike" if is_target else ("off" if session_role == "off" else "run")
        tss = 60.0 if is_target else (0.0 if session_role == "off" else 20.0)
        daily_plan.append(
            (
                datetime.combine(session_date, datetime.min.time()),
                tss,
                {} if sport == "off" else {sport: tss},
            )
        )
        templates.append(
            {
                "date": session_date.isoformat(),
                "session_role": session_role,
                "session_focus": "Качество • вело" if is_target else "Лёгкая • бег",
                "sport": sport,
                "sport_label": "вело" if is_target else "бег",
                "duration_minutes": 60 if is_target else 30,
                "phase": "Build",
            }
        )
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "event_date": (today + timedelta(days=60)).isoformat(),
        "weeks_to_race": 8,
        "start_week": monday,
        "weekly_tss_plan": [100, 100],
        "base_weekly_tss_plan": [100, 100],
        "phases": ["Build", "Build"],
        "daily_plan": daily_plan,
        "session_templates": templates,
        "weekly_summary": [],
        "constraint_summary": {},
        "near_term_edit_version": 0,
    }


def _save_prediction(
    db: Database,
    *,
    fingerprint: str,
    created_at: str,
    prediction_pct: int,
    target_key: str | None = None,
) -> dict:
    checkpoint = db.get_latest_planning_checkpoint()
    if checkpoint is None:
        checkpoint = db.save_planning_checkpoint(
            build_planning_checkpoint(_goal_plan(date(2026, 7, 12)))
        )
    plan = checkpoint["goal_plan_snapshot"]
    plan_session_index = next(
        index
        for index, template in enumerate(plan["session_templates"])
        if template["date"] == "2026-07-14"
    )
    resolved_target_key = target_key or (
        f"{checkpoint['id']}:2026-07-14:{plan_session_index}:{RULE_VERSION}"
    )
    return db.save_session_quality_prediction(
        fingerprint=fingerprint,
        target_key=resolved_target_key,
        rule_version=RULE_VERSION,
        target_date="2026-07-14",
        plan_checkpoint_id=checkpoint["id"],
        plan_session_index=plan_session_index,
        planned_session=_planned(),
        forecast={
            "prediction_pct": prediction_pct,
            "prediction_band": (
                "low" if prediction_pct < 60 else "uncertain" if prediction_pct < 75 else "high"
            ),
        },
        inputs={"readiness": _readiness()},
        evidence=["pre-registered evidence"],
        created_at=created_at,
    )


def test_v1_formula_matches_pre_registered_examples_and_rejects_low_confidence() -> None:
    quality = build_session_quality_forecast(_readiness(), _planned())
    low = build_session_quality_forecast(_readiness(35.0), _planned())
    long = build_session_quality_forecast(
        _readiness(80.0, 1.0),
        _planned(role="long", tss=20.0, duration=50),
    )

    assert quality["rule_version"] == "session_quality_v1"
    assert quality["prediction_pct"] == 68
    assert quality["prediction_band"] == "uncertain"
    assert quality["demand"]["density_tss_per_hour"] == 60.0
    assert low["prediction_pct"] == 36
    assert low["prediction_band"] == "low"
    assert long["prediction_pct"] == 83
    assert long["prediction_band"] == "high"
    assert build_session_quality_forecast(_readiness(75.0, 0.59), _planned()) is None
    assert build_session_quality_forecast({**_readiness(), "stale": True}, _planned()) is None


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ({"role": "quality", "sport": "bike", "tss": 48}, "exact"),
        ({"role": "quality", "sport": "bike", "tss": 72}, "exact"),
        ({"role": "quality", "sport": "run", "tss": 36}, "substituted"),
        ({"role": "quality", "sport": "bike", "tss": 84}, "substituted"),
        ({"role": "easy", "sport": "bike", "tss": 60}, "major_deviation"),
        ({"role": "quality", "sport": "bike", "tss": 35}, "major_deviation"),
        ({"role": None, "sport": "bike", "tss": 60}, None),
    ],
)
def test_adherence_boundaries_are_operational(actual: dict, expected: str | None) -> None:
    assert classify_plan_adherence(_planned(), actual) == expected


def test_brier_uses_only_unambiguous_quality_ratings() -> None:
    assert brier_score(70, 5) == 0.09
    assert brier_score(30, 1) == 0.09
    assert brier_score(70, 3) is None
    assert brier_score(70, None) is None


def test_activity_processor_preserves_only_source_backed_gmt_start() -> None:
    rows = ActivityProcessor.process_activities(
        [
            {
                "activityId": "with-gmt",
                "startTimeLocal": "2026-07-14T11:00:00",
                "startTimeGMT": "2026-07-14T08:00:00",
                "activityType": {"typeKey": "cycling"},
                "duration": 3600,
            },
            {
                "activityId": "local-only",
                "startTimeLocal": "2026-07-14T12:00:00",
                "activityType": {"typeKey": "running"},
                "duration": 1800,
            },
        ]
    ).set_index("activity_id")

    assert rows.loc["with-gmt", "started_at_utc"] == "2026-07-14T08:00:00Z"
    assert pd.isna(rows.loc["local-only", "started_at_utc"])
    assert rows.loc["local-only", "date"].date().isoformat() == "2026-07-14"


def test_database_forecast_fingerprint_is_idempotent_and_snapshots_are_immutable(tmp_path) -> None:
    db = Database(str(tmp_path / "prediction-log.db"))

    first = _save_prediction(
        db,
        fingerprint="forecast-1",
        created_at="2026-07-14T06:00:00Z",
        prediction_pct=40,
    )
    duplicate = _save_prediction(
        db,
        fingerprint="forecast-1",
        created_at="2026-07-14T06:01:00Z",
        prediction_pct=90,
    )
    second = _save_prediction(
        db,
        fingerprint="forecast-2",
        created_at="2026-07-14T07:00:00Z",
        prediction_pct=70,
    )

    assert first["created"] is True
    assert duplicate["created"] is False
    assert duplicate["prediction"]["id"] == first["prediction"]["id"]
    assert duplicate["prediction"]["prediction_pct"] == 40
    assert second["prediction"]["revision"] == 2
    assert len(db.get_session_quality_predictions(days=36500)) == 2


def test_database_serializes_concurrent_revisions(tmp_path) -> None:
    db = Database(str(tmp_path / "concurrent-revisions.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(date(2026, 7, 12))))
    barrier = Barrier(2)

    def save(sequence: int) -> dict:
        barrier.wait()
        return _save_prediction(
            db,
            fingerprint=f"concurrent-{sequence}",
            created_at=f"2026-07-14T0{sequence + 5}:00:00Z",
            prediction_pct=40 + sequence,
        )["prediction"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        rows = list(executor.map(save, (1, 2)))

    assert {row["revision"] for row in rows} == {1, 2}
    assert len(db.get_session_quality_predictions(days=36500)) == 2


def test_database_migrates_legacy_activity_schema_with_null_start(tmp_path) -> None:
    db_path = tmp_path / "legacy-activities.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE activities (
                activity_id TEXT PRIMARY KEY,
                date DATE,
                sport TEXT,
                duration_minutes REAL,
                tss REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO activities (activity_id, date, sport, duration_minutes, tss) VALUES ('old', '2026-07-01', 'bike', 30, 20)"
        )

    db = Database(str(db_path))
    old = db.get_activities_by_ids(["old"])[0]

    assert old["started_at_utc"] is None
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(activities)")}
    assert "started_at_utc" in columns


def test_prediction_journal_participates_in_database_stats_and_clear(tmp_path) -> None:
    db = Database(str(tmp_path / "stats-clear.db"))
    _save_prediction(
        db,
        fingerprint="stats-forecast",
        created_at="2026-07-14T06:00:00Z",
        prediction_pct=50,
    )

    assert db.get_database_stats()["session_quality_predictions"] == 1
    db.clear_all_data()
    assert db.get_database_stats()["session_quality_predictions"] == 0


def test_resolution_scores_latest_prestart_revision_and_freezes_actual_snapshot(tmp_path) -> None:
    from api.session_quality_forecast import resolve_session_quality_prediction

    db = Database(str(tmp_path / "resolve.db"))
    first = _save_prediction(
        db,
        fingerprint="forecast-1",
        created_at="2026-07-14T06:00:00Z",
        prediction_pct=40,
    )["prediction"]
    _save_prediction(
        db,
        fingerprint="forecast-2",
        created_at="2026-07-14T07:00:00Z",
        prediction_pct=70,
    )
    _save_prediction(
        db,
        fingerprint="forecast-3",
        created_at="2026-07-14T09:00:00Z",
        prediction_pct=90,
    )
    db.save_activities(
        [
            {
                "activity_id": "activity-1",
                "date": "2026-07-14",
                "started_at_utc": "2026-07-14T08:00:00Z",
                "sport": "bike",
                "duration_minutes": 60,
                "tss": 60,
            }
        ]
    )

    resolved = resolve_session_quality_prediction(
        db,
        first["id"],
        activity_ids=["activity-1"],
        actual_role="quality",
        quality_rating_1_5=4,
        note="Контролируемо выполнил интервалы",
    )
    by_revision = {row["revision"]: row for row in resolved["predictions"]}

    assert by_revision[1]["status"] == "unscored"
    assert by_revision[1]["unscored_reason"] == "superseded"
    assert by_revision[2]["status"] == "scored"
    assert by_revision[2]["plan_adherence"] == "exact"
    assert by_revision[2]["quality_outcome"] == "success"
    assert by_revision[2]["brier_score"] == 0.09
    assert by_revision[2]["actual_snapshot"]["actual_total_tss"] == 60.0
    assert by_revision[3]["unscored_reason"] == "post_start_prediction"

    legacy_upsert_activities(
        db,
        [
            {
                "activity_id": "activity-1",
                "date": "2026-07-14",
                "started_at_utc": "2026-07-14T08:00:00Z",
                "sport": "bike",
                "duration_minutes": 60,
                "tss": 10,
            }
        ]
    )
    from api.session_feedback import project_predictions_with_evaluations

    frozen = next(
        row
        for row in project_predictions_with_evaluations(
            db,
            db.get_session_quality_predictions(days=36500),
        )
        if row["id"] == by_revision[2]["id"]
    )
    assert frozen["actual_snapshot"]["actual_total_tss"] == 60.0
    assert frozen["brier_score"] == 0.09
    raw = db.get_session_quality_prediction(by_revision[2]["id"])
    assert raw["status"] == "pending"
    assert raw["actual_snapshot"] == {}


def test_major_deviation_is_unscored_even_with_clear_rating(tmp_path) -> None:
    from api.session_quality_forecast import resolve_session_quality_prediction

    db = Database(str(tmp_path / "major-deviation.db"))
    prediction = _save_prediction(
        db,
        fingerprint="forecast-major",
        created_at="2026-07-14T06:00:00Z",
        prediction_pct=30,
    )["prediction"]
    db.save_activities(
        [
            {
                "activity_id": "walk-1",
                "date": "2026-07-14",
                "started_at_utc": "2026-07-14T08:00:00Z",
                "sport": "walk",
                "duration_minutes": 30,
                "tss": 5,
            }
        ]
    )

    resolved = resolve_session_quality_prediction(
        db,
        prediction["id"],
        activity_ids=["walk-1"],
        actual_role="recovery",
        quality_rating_1_5=5,
    )["predictions"][0]

    assert resolved["status"] == "unscored"
    assert resolved["plan_adherence"] == "major_deviation"
    assert resolved["unscored_reason"] == "major_deviation"
    assert resolved["brier_score"] is None


@pytest.mark.parametrize(
    ("started_at_utc", "rating", "expected_reason"),
    [
        (None, 5, "missing_session_start"),
        ("2026-07-14T08:00:00Z", 3, "ambiguous_quality"),
    ],
)
def test_missing_start_or_ambiguous_rating_is_explicitly_unscored(
    tmp_path,
    started_at_utc: str | None,
    rating: int,
    expected_reason: str,
) -> None:
    from api.session_quality_forecast import resolve_session_quality_prediction

    db = Database(str(tmp_path / f"{expected_reason}.db"))
    prediction = _save_prediction(
        db,
        fingerprint=f"forecast-{expected_reason}",
        created_at="2026-07-14T06:00:00Z",
        prediction_pct=50,
    )["prediction"]
    db.save_activities(
        [
            {
                "activity_id": "activity-1",
                "date": "2026-07-14",
                "started_at_utc": started_at_utc,
                "sport": "bike",
                "duration_minutes": 60,
                "tss": 60,
            }
        ]
    )

    resolved = resolve_session_quality_prediction(
        db,
        prediction["id"],
        activity_ids=["activity-1"],
        actual_role="quality",
        quality_rating_1_5=rating,
    )["predictions"][0]

    assert resolved["status"] == "unscored"
    assert resolved["unscored_reason"] == expected_reason
    assert resolved["brier_score"] is None


def test_invalid_resolution_evidence_does_not_partially_update(tmp_path) -> None:
    from api.session_quality_forecast import resolve_session_quality_prediction

    db = Database(str(tmp_path / "invalid-resolution.db"))
    prediction = _save_prediction(
        db,
        fingerprint="forecast-invalid",
        created_at="2026-07-14T06:00:00Z",
        prediction_pct=50,
    )["prediction"]

    with pytest.raises(LookupError, match="activities not found"):
        resolve_session_quality_prediction(
            db,
            prediction["id"],
            activity_ids=["unknown"],
            actual_role="quality",
            quality_rating_1_5=4,
        )
    with pytest.raises(ValueError, match="between 1 and 5"):
        resolve_session_quality_prediction(
            db,
            prediction["id"],
            activity_ids=[],
            actual_role="quality",
            quality_rating_1_5=6,
        )

    unchanged = db.get_session_quality_prediction(prediction["id"])
    assert unchanged["status"] == "pending"
    assert unchanged["actual_snapshot"] == {}


def test_shadow_recording_appends_changed_readiness_without_product_mutation(
    tmp_path,
) -> None:
    from api.session_quality_forecast import record_shadow_session_quality_forecast

    today = date(2026, 7, 12)
    db = Database(str(tmp_path / "shadow.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    before_checkpoint = db.get_latest_planning_checkpoint()["id"]

    first = record_shadow_session_quality_forecast(
        db,
        checkpoint=checkpoint,
        readiness_snapshot=_readiness(75.0),
        today=today,
    )
    repeat = record_shadow_session_quality_forecast(
        db,
        checkpoint=checkpoint,
        readiness_snapshot=_readiness(75.0),
        today=today,
    )
    second = record_shadow_session_quality_forecast(
        db,
        checkpoint=checkpoint,
        readiness_snapshot=_readiness(35.0),
        today=today,
    )

    assert first["prediction"]["id"] == repeat["prediction"]["id"]
    assert second["prediction"]["revision"] == 2
    assert len(db.get_session_quality_predictions(days=36500)) == 2
    assert db.get_latest_planning_checkpoint()["id"] == before_checkpoint
    assert db.get_recovery_decisions(days=36500) == []
    assert db.get_coach_proposals(days=36500) == []


def test_shadow_recording_reuses_semantic_forecast_when_only_provenance_timestamps_change(
    tmp_path,
) -> None:
    from api.session_quality_forecast import record_shadow_session_quality_forecast

    today = date(2026, 7, 12)
    db = Database(str(tmp_path / "timestamp-replay.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    results = []
    for minute in range(10):
        observed_at = f"2026-07-12T06:{minute:02d}:00Z"
        readiness = {
            **_readiness(),
            "observed_at_utc": observed_at,
            "provenance": {"observed_at_utc": observed_at},
        }
        report = {
            "as_of": today.isoformat(),
            "readiness": {
                **readiness,
                "observed_at_utc": observed_at,
                "provenance": {"observed_at_utc": observed_at},
            },
        }
        results.append(
            record_shadow_session_quality_forecast(
                db,
                report=report,
                checkpoint=checkpoint,
                readiness_snapshot=readiness,
                today=today,
            )
        )

    assert results[0]["created"] is True
    assert all(result["created"] is False for result in results[1:])
    assert {result["prediction"]["id"] for result in results} == {
        results[0]["prediction"]["id"]
    }
    rows = db.get_session_quality_predictions(days=36500)
    assert len(rows) == 1
    assert rows[0]["inputs"]["readiness"]["observed_at_utc"] == "2026-07-12T06:00:00Z"
    assert rows[0]["inputs"]["gate_readiness"]["provenance"]["observed_at_utc"] == (
        "2026-07-12T06:00:00Z"
    )


def test_shadow_recording_concurrent_semantic_replays_converge(tmp_path) -> None:
    from api.session_quality_forecast import record_shadow_session_quality_forecast

    today = date(2026, 7, 12)
    db = Database(str(tmp_path / "concurrent-semantic-replay.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    barrier = Barrier(2)

    def record(minute: int) -> dict:
        observed_at = f"2026-07-12T06:{minute:02d}:00Z"
        readiness = {
            **_readiness(),
            "observed_at_utc": observed_at,
            "provenance": {"observed_at_utc": observed_at},
        }
        barrier.wait()
        return record_shadow_session_quality_forecast(
            db,
            checkpoint=checkpoint,
            readiness_snapshot=readiness,
            today=today,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(record, (0, 1)))

    assert sum(result["created"] for result in results) == 1
    assert {result["prediction"]["id"] for result in results} == {
        results[0]["prediction"]["id"]
    }
    assert len(db.get_session_quality_predictions(days=36500)) == 1


def test_shadow_recording_stops_after_confirmed_actual_start(tmp_path) -> None:
    from api.session_quality_forecast import record_shadow_session_quality_forecast

    today = date(2026, 7, 12)
    db = Database(str(tmp_path / "started-session.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    plan = checkpoint["goal_plan_snapshot"]
    target_index = next(
        index
        for index, template in enumerate(plan["session_templates"])
        if template["date"] == "2026-07-14"
    )
    template = plan["session_templates"][target_index]
    session_id = template["session_id"]
    first = record_shadow_session_quality_forecast(
        db,
        checkpoint=checkpoint,
        readiness_snapshot=_readiness(),
        today=today,
    )
    db.save_activities(
        [
            {
                "activity_id": "confirmed-ride",
                "date": "2026-07-14",
                "started_at_utc": "2026-07-14T08:00:00Z",
                "sport": "bike",
                "duration_minutes": 60,
                "tss": 60,
            }
        ]
    )
    db.save_plan_actual_match(
        {
            "fingerprint": "confirmed-match-1",
            "target_key": f"session:{session_id}",
            "session_id": session_id,
            "base_checkpoint_id": checkpoint["id"],
            "session_date": "2026-07-14",
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "planned_snapshot": {
                "session_id": session_id,
                "date": "2026-07-14",
                "role": "quality",
                "sport": "bike",
                "tss": 60.0,
                "duration_minutes": 60,
            },
            "actual_activity_ids": ["confirmed-ride"],
            "actual_snapshot": {"role": "quality", "sport": "bike", "tss": 60.0},
            "evidence": ["confirmed in the plan-fact ledger"],
            "rule_version": "plan_actual_match_v2",
        }
    )

    after_start = record_shadow_session_quality_forecast(
        db,
        checkpoint=checkpoint,
        readiness_snapshot=_readiness(),
        today=today,
    )

    assert first["created"] is True
    assert after_start == {"prediction": None, "reason": "session_started"}
    assert len(db.get_session_quality_predictions(days=36500)) == 1


def test_shadow_recording_stops_after_active_terminal_feedback(tmp_path) -> None:
    from api.session_quality_forecast import record_shadow_session_quality_forecast
    from models.post_workout_feedback import FEEDBACK_RULE_VERSION

    today = date(2026, 7, 12)
    db = Database(str(tmp_path / "terminal-feedback.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    plan = checkpoint["goal_plan_snapshot"]
    target_index = next(
        index
        for index, template in enumerate(plan["session_templates"])
        if template["date"] == "2026-07-14"
    )
    session_id = plan["session_templates"][target_index]["session_id"]
    first = record_shadow_session_quality_forecast(
        db,
        checkpoint=checkpoint,
        readiness_snapshot=_readiness(),
        today=today,
    )
    db.save_session_feedback(
        {
            "fingerprint": "terminal-feedback-1",
            "target_key": f"session:{session_id}",
            "session_id": session_id,
            "match_snapshot": {"planned": {"session_id": session_id}},
            "actual_activity_ids": [],
            "completion_status": "unknown",
            "completion_pct": None,
            "completion_pct_source": "athlete_entered",
            "session_rpe_1_10": None,
            "quality_rating_1_5": None,
            "note": "athlete submitted an uncertain outcome",
            "source": "user_web",
            "session_end_provenance": "athlete_entered",
            "status": "active",
            "rule_version": FEEDBACK_RULE_VERSION,
            "submitted_at": "2026-07-14T10:00:00Z",
        }
    )

    after_feedback = record_shadow_session_quality_forecast(
        db,
        checkpoint=checkpoint,
        readiness_snapshot=_readiness(),
        today=today,
    )

    assert first["created"] is True
    assert after_feedback == {"prediction": None, "reason": "terminal_feedback_exists"}
    assert len(db.get_session_quality_predictions(days=36500)) == 1


def test_summary_counts_only_scored_low_forecast_failures(tmp_path) -> None:
    from api.session_quality_forecast import summarize_session_quality_predictions

    rows = [
        {"status": "scored", "prediction_pct": 40, "quality_outcome": "failure", "brier_score": 0.16},
        {"status": "scored", "prediction_pct": 50, "quality_outcome": "success", "brier_score": 0.25},
        {"status": "unscored", "prediction_pct": 30, "quality_outcome": None, "unscored_reason": "major_deviation"},
    ]

    summary = summarize_session_quality_predictions(rows)

    assert summary["total"] == 3
    assert summary["scored"] == 2
    assert summary["unscored"] == 1
    assert summary["mean_brier_score"] == 0.205
    assert summary["low_forecast_count"] == 2
    assert summary["low_forecast_hit_rate"] == 0.5
    assert summary["unscored_reasons"] == {"major_deviation": 1}


def test_openapi_exposes_headless_prediction_list_and_resolve() -> None:
    from api.main import app

    paths = app.openapi()["paths"]
    assert "/api/session-quality-predictions" in paths
    assert "/api/session-quality-predictions/{prediction_id}/resolve" in paths


def test_post_sync_shadow_failure_is_non_fatal(tmp_path, monkeypatch) -> None:
    from api.routers import system as system_router

    db = Database(str(tmp_path / "sync-shadow.db"))
    monkeypatch.setattr(
        system_router,
        "record_shadow_session_quality_forecast",
        lambda _db: (_ for _ in ()).throw(RuntimeError("shadow unavailable")),
    )

    payload = system_router._attach_shadow_forecast(
        {"sync_state": "succeeded"},
        db,
    )

    assert payload["sync_state"] == "succeeded"
    assert payload["session_quality_forecast"] is None
    assert payload["session_quality_forecast_error"] == "shadow unavailable"


def test_woz_schema_migration_preserves_reaction_and_note(tmp_path) -> None:
    from scripts.migrate_woz_tracking_quality import migrate

    path = tmp_path / "woz.csv"
    rows = [
        ["дата", "прогноз_попал", "реакция_1_5", "заметка"],
        ["2026-07-10", "да", "4", "reaction present"],
        ["2026-07-11", "unscored", "reaction omitted"],
    ]
    with path.open("w", encoding="utf-8", newline="") as target:
        csv.writer(target).writerows(rows)

    assert migrate(path) is True
    assert migrate(path) is False
    with path.open("r", encoding="utf-8", newline="") as source:
        migrated = list(csv.reader(source))

    assert migrated[0] == [
        "дата",
        "прогноз_попал",
        "качество_сессии_1_5",
        "реакция_1_5",
        "заметка",
    ]
    assert migrated[1][-2:] == ["4", "reaction present"]
    assert migrated[2][-2:] == ["", "reaction omitted"]
    assert {len(row) for row in migrated} == {5}

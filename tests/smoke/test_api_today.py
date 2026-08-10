"""Behavior contract for issues #158/#174: canonical daily decision snapshot.

Специфицирует композицию канонического readiness snapshot, salience-gate
(RecoveryReplanLoop) и активного плана в один утренний payload с каскадом
состояний no_plan → data_gap → conflict_actionable/conflict_unactionable → silence.
Contributor-safe:
временный SQLite, отчёт gate и snapshot подменяются monkeypatch там, где
нужен управляемый исход (тот же паттерн, что tests/smoke/test_recovery_replan_loop.py).
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint


def _goal_plan(today: date, *, target_days_until: int = 0, target_role: str = "quality") -> dict:
    monday = today - timedelta(days=today.weekday())
    target_date = today + timedelta(days=target_days_until)
    daily_plan = []
    templates = []
    for index in range(21):
        session_date = monday + timedelta(days=index)
        is_target = session_date == target_date
        role = target_role if is_target else ("off" if index % 7 == 0 else "easy")
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

    weekly_summary = []
    for week_index in range(3):
        start = week_index * 7
        weekly_summary.append(
            {
                "week_start": monday + timedelta(days=start),
                "phase": "Build",
                "weekly_tss": int(sum(row[1] for row in daily_plan[start : start + 7])),
                "capacity_tss": 250,
                "adjustment_note": "—",
            }
        )

    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "event_date": (today + timedelta(days=70)).isoformat(),
        "weeks_to_race": 10,
        "start_week": monday,
        "weekly_tss_plan": [row["weekly_tss"] for row in weekly_summary],
        "base_weekly_tss_plan": [row["weekly_tss"] for row in weekly_summary],
        "phases": ["Build", "Build", "Build"],
        "daily_plan": daily_plan,
        "session_templates": templates,
        "weekly_summary": weekly_summary,
        "constraint_summary": {
            "current_tsb": -18.0,
            "load_state": "fatigued",
            "load_state_label": "Накопленная усталость",
            "notes": [],
        },
        "near_term_edit_version": 0,
        "near_term_edit_rollback_target_checkpoint_id": None,
    }


def _session(today: date, *, days_until: int, role: str, tss: float = 20.0) -> dict:
    session_date = today + timedelta(days=days_until)
    return {
        "date": session_date.isoformat(),
        "days_until": days_until,
        "role": role,
        "tss": tss,
        "name": "Качество • вело" if role == "quality" else "Лёгкая • бег",
        "sport_label": "вело" if role == "quality" else "бег",
        "phase": "Build",
    }


def _report(
    today: date,
    *,
    sessions: list[dict] | None = None,
    conflicts: list[dict] | None = None,
    data_gap: bool = False,
    score: float | None = 72.0,
    status: str = "ready",
) -> dict:
    sessions = sessions or []
    conflicts = conflicts or []
    return {
        "as_of": today.isoformat(),
        "horizon_days": 4,
        "base_horizon_days": 3,
        "lookahead_policy": "base_plus_nearest_quality",
        "horizon_extended_for_quality": False,
        "quality_lookahead_session": None,
        "readiness": {
            "score": None if data_gap else score,
            "status": "unknown" if data_gap else status,
            "confidence": 0.0 if data_gap else 0.8,
        },
        "sessions_evaluated": sessions,
        "conflicts": conflicts,
        "silence": not conflicts,
        "data_gap": data_gap,
        "reason": "Недостаточно данных." if data_gap else (
            "Готовность low расходится с планом." if conflicts else "План и состояние согласны."
        ),
    }


def _conflict_for(session: dict, *, status: str = "low", severity: str = "high") -> dict:
    return {
        "date": session["date"],
        "days_until": session["days_until"],
        "severity": severity,
        "kind": f"{status}_readiness_{session['role']}_session",
        "session": {
            "name": session["name"],
            "role": session["role"],
            "tss": session["tss"],
            "sport_label": session["sport_label"],
        },
        "evidence": [
            "Готовность 35/100 (low): HRV -18% к базе",
            "Сегодня: Качество • вело, 60 TSS",
        ],
    }


def _snapshot(*, score: float | None = 72.0, status: str = "ready") -> dict:
    return {
        "score": score,
        "status": status if score is not None else "unknown",
        "computed_at": None,
        "is_provisional": False,
        "source_completeness": 1.0,
        "factors": [
            {"key": "hrv", "label": "HRV", "evidence": "HRV 41 (+17% к базе)"},
        ],
        "missing_inputs": [],
        "stale": False,
        "reason": "Readiness рассчитан по полному набору основных recovery-сигналов.",
        "drivers": [{"key": "hrv", "evidence": "HRV 41 (+17% к базе)"}],
        "tsb": {"ctl": 18.7, "atl": 36.2, "tsb": -17.5, "window_days": 90},
        "confidence": 0.8,
    }


def _patch_report(monkeypatch, report: dict) -> None:
    from api import recovery_replan_loop as loop_module

    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)


def _patch_snapshot(monkeypatch, snapshot: dict) -> None:
    from api import today_snapshot as today_module

    monkeypatch.setattr(today_module, "build_readiness_snapshot", lambda _db: snapshot)


def test_today_empty_db_is_no_plan(tmp_path) -> None:
    from api.routers.today import today_view

    db = Database(str(tmp_path / "empty.db"))
    payload = today_view(db=db)

    assert payload["state"] == "no_plan"
    assert payload["snapshot_version"] == "today_decision_snapshot_v2"
    assert payload["primary_action"]["kind"] == "open_planning"
    assert payload["proposal"]["relation"] == "none"
    assert payload["forecast"]["affects_decision"] is False
    assert payload["pending_proposal"] is None
    assert payload["session"] is None
    assert payload["reason"]
    assert payload["readiness_source"] == "canonical_snapshot"
    assert payload["operational_state"]["status"] == "empty"


def test_today_data_gap_names_reason_without_proposal(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "gap.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    _patch_report(monkeypatch, _report(today, data_gap=True))
    _patch_snapshot(monkeypatch, _snapshot(score=None))

    payload = today_view(db=db)

    assert payload["state"] == "data_gap"
    assert "Недостаточно" in payload["reason"]
    assert payload["pending_proposal"] is None
    assert payload["readiness"] is None
    assert payload["session"]["date"] == today.isoformat()
    assert payload["session"]["role"] == "quality"
    assert payload["session"]["session_id"]
    assert payload["primary_action"]["kind"] == "sync_or_wait"


def test_today_silence_projects_day_session_and_canonical_readiness(
    tmp_path, monkeypatch
) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "silence.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today, target_role="easy")))
    day_session = _session(today, days_until=0, role="easy")
    _patch_report(monkeypatch, _report(today, sessions=[day_session]))
    _patch_snapshot(monkeypatch, _snapshot(score=72.0))

    payload = today_view(db=db)

    assert payload["state"] == "silence"
    assert payload["date"] == today.isoformat()
    assert payload["session"]["role"] == "easy"
    assert payload["session"]["role_label"] == "лёгкая"
    assert payload["session"]["is_key"] is False
    assert payload["gate"]["outcome"] == "silence"
    assert payload["primary_action"]["kind"] == "follow_plan"


def test_today_projects_persisted_catalog_prescription(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "catalog-today.db"))
    goal_plan = _goal_plan(today, target_role="quality")
    target_index = next(
        index
        for index, template in enumerate(goal_plan["session_templates"])
        if template["date"] == today.isoformat()
    )
    goal_plan["session_templates"][target_index].update(
        {
            "kind": "single",
            "catalog_version": "workout_catalog_v1",
            "template_key": "bike_threshold_intervals",
            "template_version": 1,
            "template_name": "Threshold Intervals",
            "stimulus": "lactate-threshold development",
            "fatigue_cost": [3, 1, 1],
            "expected_recovery_hours": 36,
            "materialization_status": "materialized",
            "target_provenance": {
                "kind": "ftp",
                "source": "athlete_profile.ftp",
                "value": 200.0,
                "fallback": False,
            },
            "materialized_steps": [
                {
                    "name": "Threshold intervals",
                    "intensity": "work",
                    "duration_seconds": 1620,
                    "target": {"type": "power", "unit": "watts", "low": 194, "high": 206},
                }
            ],
        }
    )
    db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))
    session = _session(today, days_until=0, role="quality", tss=60.0)
    _patch_report(monkeypatch, _report(today, sessions=[session]))
    _patch_snapshot(monkeypatch, _snapshot(score=72.0))

    payload = today_view(db=db)
    projected = payload["session"]

    assert projected["template_key"] == "bike_threshold_intervals"
    assert projected["template_name"] == "Threshold Intervals"
    assert projected["stimulus"] == "lactate-threshold development"
    assert projected["fatigue_cost"] == [3, 1, 1]
    assert projected["expected_recovery_hours"] == 36
    assert projected["target_provenance"]["kind"] == "ftp"
    assert projected["steps"][0]["duration_seconds"] == 1620
    assert projected["legs"] == []
    assert payload["readiness"]["score"] == 72.0
    assert payload["readiness"]["drivers"], "evidence-раскрытие требует drivers"
    assert payload["readiness_source"] == "canonical_snapshot"
    assert payload["pending_proposal"] is None
    assert payload["loop_outcome"] == "silence"


def test_today_conflict_exposes_pending_proposal_idempotently(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "conflict.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    day_session = _session(today, days_until=0, role="quality", tss=60.0)
    report = _report(
        today,
        sessions=[day_session],
        conflicts=[_conflict_for(day_session)],
        score=35.0,
        status="low",
    )
    _patch_report(monkeypatch, report)
    _patch_snapshot(monkeypatch, _snapshot(score=35.0, status="low"))

    first = today_view(db=db)
    second = today_view(db=db)

    assert first["state"] == "conflict_actionable"
    assert first["primary_action"]["kind"] == "review_proposal"
    assert first["proposal"]["relation"] == "current"
    assert first["session"]["is_key"] is True
    assert first["pending_proposal"] is not None
    assert first["pending_proposal"]["action"] == "recovery_replan"
    assert first["pending_proposal"]["status"] == "pending"
    assert second["pending_proposal"]["id"] == first["pending_proposal"]["id"]
    assert len(db.get_coach_proposals(days=36500)) == 1


def test_today_conflict_without_safe_proposal_is_explicitly_unactionable(
    tmp_path, monkeypatch
) -> None:
    """Issue #174 regression: a real gate conflict must never look like silence."""
    from api import today_snapshot as snapshot_module
    from api.routers import today as today_module

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "unactionable.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    day_session = _session(today, days_until=0, role="quality", tss=60.0)
    report = _report(
        today,
        sessions=[day_session],
        conflicts=[_conflict_for(day_session)],
        score=35.0,
        status="low",
    )
    monkeypatch.setattr(
        snapshot_module,
        "_run_loop",
        lambda _db, **_kwargs: {
            "outcome": "conflict",
            "decision": {"id": 17, "fingerprint": "conflict-gap"},
            "proposal": None,
            "proposal_gap": "protected_date",
            "readiness_conflicts": report,
            "session_quality_forecast": None,
            "session_quality_forecast_error": None,
        },
    )
    _patch_snapshot(monkeypatch, _snapshot(score=35.0, status="low"))

    payload = today_module.today_view(db=db)

    assert payload["state"] == "conflict_unactionable"
    assert payload["primary_action"]["kind"] == "inspect_evidence"
    assert payload["pending_proposal"] is None
    assert payload["proposal"]["relation"] == "none"
    assert payload["gate"]["proposal_gap"] == "protected_date"
    assert payload["gate"]["conflicts"] == report["conflicts"]
    assert "План в силе" not in payload["reason"]


def test_today_keeps_current_pending_proposal_visible_when_latest_loop_is_silent(
    tmp_path, monkeypatch
) -> None:
    from api import today_snapshot as snapshot_module
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "pending-survives.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    proposal = db.save_coach_proposal(
        action="recovery_replan",
        params={"base_checkpoint_id": checkpoint["id"]},
        preview={"reason": "earlier conflict"},
        source="recovery_replan",
        source_key="earlier-conflict",
        active_key="same-session",
    )
    report = _report(today)
    monkeypatch.setattr(
        snapshot_module,
        "_run_loop",
        lambda _db, **_kwargs: {
            "outcome": "silence",
            "decision": {"id": 18, "fingerprint": "later-silence"},
            "proposal": None,
            "readiness_conflicts": report,
        },
    )
    _patch_snapshot(monkeypatch, _snapshot())

    payload = today_view(db=db)

    assert payload["state"] == "conflict_actionable"
    assert payload["pending_proposal"]["id"] == proposal["id"]
    assert payload["proposal"]["relation"] == "current"


def test_today_stale_pending_proposal_is_evidence_without_controls(
    tmp_path, monkeypatch
) -> None:
    from api import today_snapshot as snapshot_module
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "stale-proposal.db"))
    old_checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    stale = db.save_coach_proposal(
        action="recovery_replan",
        params={"base_checkpoint_id": old_checkpoint["id"]},
        preview={"reason": "old plan"},
        source="recovery_replan",
        source_key="stale-conflict",
        active_key="stale-session",
    )
    current_checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    day_session = _session(today, days_until=0, role="quality", tss=60.0)
    report = _report(today, sessions=[day_session], conflicts=[_conflict_for(day_session)])
    monkeypatch.setattr(
        snapshot_module,
        "_run_loop",
        lambda _db, **_kwargs: {
            "outcome": "conflict",
            "decision": {"id": 19, "fingerprint": "current-conflict"},
            "proposal": None,
            "proposal_gap": "stale checkpoint",
            "readiness_conflicts": report,
        },
    )
    _patch_snapshot(monkeypatch, _snapshot(score=35.0, status="low"))

    payload = today_view(db=db)

    assert payload["state"] == "conflict_unactionable"
    assert payload["pending_proposal"] is None
    assert payload["proposal"]["relation"] == "stale"
    assert payload["proposal"]["proposal"]["id"] == stale["id"]
    assert payload["proposal"]["active_checkpoint_id"] == current_checkpoint["id"]


def test_today_failed_proposal_remains_unactionable(tmp_path, monkeypatch) -> None:
    from api import today_snapshot as snapshot_module
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "failed.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    day_session = _session(today, days_until=0, role="quality", tss=60.0)
    report = _report(today, sessions=[day_session], conflicts=[_conflict_for(day_session)])
    failed = {
        "id": 20,
        "action": "recovery_replan",
        "status": "failed",
        "params": {"base_checkpoint_id": checkpoint["id"]},
        "error": "apply failed",
    }
    monkeypatch.setattr(
        snapshot_module,
        "_run_loop",
        lambda _db, **_kwargs: {
            "outcome": "conflict",
            "decision": {"id": 20, "fingerprint": "failed-conflict"},
            "proposal": failed,
            "readiness_conflicts": report,
        },
    )
    _patch_snapshot(monkeypatch, _snapshot(score=35.0, status="low"))

    payload = today_view(db=db)

    assert payload["state"] == "conflict_unactionable"
    assert payload["proposal"]["relation"] == "resolved"
    assert payload["proposal"]["proposal"]["status"] == "failed"
    assert payload["pending_proposal"] is None


def test_today_resolved_conflict_returns_to_silence(tmp_path, monkeypatch) -> None:
    """Решение принято сегодня → экран не возвращает пользователя в тревогу."""
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "resolved.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    day_session = _session(today, days_until=0, role="quality", tss=60.0)
    report = _report(
        today,
        sessions=[day_session],
        conflicts=[_conflict_for(day_session)],
        score=35.0,
        status="low",
    )
    _patch_report(monkeypatch, report)
    _patch_snapshot(monkeypatch, _snapshot(score=35.0, status="low"))

    first = today_view(db=db)
    db.update_coach_proposal_status(
        first["pending_proposal"]["id"], "rejected", result={"message": "rejected by user"}
    )

    payload = today_view(db=db)

    assert payload["state"] == "silence"
    assert payload["loop_outcome"] == "conflict"
    assert payload["pending_proposal"] is None
    assert payload["proposal"]["relation"] == "resolved"


def test_today_summarizes_yesterday_fact(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = datetime.now().date()
    yesterday = (today - timedelta(days=1)).isoformat()
    db = Database(str(tmp_path / "yesterday.db"))
    db.save_planning_checkpoint(
        build_planning_checkpoint(_goal_plan(today - timedelta(days=1), target_role="easy"))
    )
    db.save_activities(
        [
            {
                "activity_id": "y1",
                "date": yesterday,
                "sport": "cycling",
                "duration_minutes": 37,
                "distance_km": 15.0,
                "tss": 21.0,
            },
            {
                "activity_id": "y2",
                "date": yesterday,
                "sport": "cycling",
                "duration_minutes": 39,
                "distance_km": 16.0,
                "tss": 16.0,
            },
        ]
    )
    _patch_report(monkeypatch, _report(today))
    _patch_snapshot(monkeypatch, _snapshot())

    payload = today_view(db=db)

    assert payload["yesterday"]["activities"] == 2
    assert payload["yesterday"]["minutes"] == 76
    assert payload["yesterday"]["tss"] == 37
    assert payload["yesterday"]["sports"] == ["cycling"]
    assert payload["yesterday"]["status"] == "available"
    assert payload["yesterday"]["matched_actual_tss"] == 37.0
    assert payload["yesterday"]["unplanned_tss"] == 0.0
    assert payload["yesterday"]["rows"]
    assert payload["yesterday"]["rule_version"] == "plan_actual_match_v1"


def test_today_selects_latest_shadow_revision_without_changing_decision(
    tmp_path, monkeypatch
) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "forecast.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    plan = checkpoint["goal_plan_snapshot"]
    session_index = next(
        index
        for index, template in enumerate(plan["session_templates"])
        if template["date"] == today.isoformat()
    )
    target_key = f"{checkpoint['id']}:{today.isoformat()}:{session_index}:session_quality_v1"
    planned = {
        "date": today.isoformat(),
        "index": session_index,
        "role": "quality",
        "sport": "bike",
        "tss": 60.0,
        "duration_minutes": 60,
    }
    for suffix, created_at, prediction_pct in (
        ("old", "2026-07-10T05:00:00Z", 44),
        ("new", "2026-07-10T06:00:00Z", 61),
    ):
        db.save_session_quality_prediction(
            fingerprint=f"forecast-{suffix}",
            target_key=target_key,
            rule_version="session_quality_v1",
            target_date=today.isoformat(),
            plan_checkpoint_id=checkpoint["id"],
            plan_session_index=session_index,
            planned_session=planned,
            forecast={
                "prediction_pct": prediction_pct,
                "prediction_band": "low" if prediction_pct < 60 else "uncertain",
            },
            inputs={"readiness_source": "canonical_snapshot"},
            evidence=[suffix],
            created_at=created_at,
        )
    day_session = _session(today, days_until=0, role="quality")
    _patch_report(monkeypatch, _report(today, sessions=[day_session]))
    _patch_snapshot(monkeypatch, _snapshot())

    payload = today_view(db=db)

    assert payload["state"] == "silence"
    assert payload["primary_action"]["kind"] == "follow_plan"
    assert payload["forecast"]["mode"] == "shadow"
    assert payload["forecast"]["affects_decision"] is False
    assert payload["forecast"]["prediction"]["prediction_pct"] == 61
    assert payload["forecast"]["relation"] == "current_checkpoint"
    assert payload["forecast"]["target_time_provenance"] == "date_only"
    assert payload["forecast"]["session_id"] == payload["session"]["session_id"]


def test_today_survives_reconciliation_failure(tmp_path, monkeypatch) -> None:
    from api import today_snapshot as snapshot_module
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "reconciliation-failure.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today, target_role="easy")))
    _patch_report(monkeypatch, _report(today))
    _patch_snapshot(monkeypatch, _snapshot())
    monkeypatch.setattr(
        snapshot_module,
        "reconciliation_at",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("matcher offline")),
    )

    payload = today_view(db=db)

    assert payload["state"] == "silence"
    assert payload["primary_action"]["kind"] == "follow_plan"
    assert payload["yesterday"]["status"] == "unavailable"
    assert "matcher offline" in payload["yesterday"]["reason"]


def test_today_composes_feedback_from_existing_yesterday_without_second_reconciliation(
    tmp_path, monkeypatch
) -> None:
    from api import today_snapshot as snapshot_module
    from api.routers.today import today_view

    today = date(2026, 7, 13)
    yesterday = today - timedelta(days=1)
    db = Database(str(tmp_path / "today-feedback.db"))
    checkpoint = db.save_planning_checkpoint(
        build_planning_checkpoint(_goal_plan(yesterday, target_role="quality"))
    )
    plan = checkpoint["goal_plan_snapshot"]
    template = next(
        item for item in plan["session_templates"] if item["date"] == yesterday.isoformat()
    )
    calls: list[dict] = []

    def fake_reconciliation(_db, **kwargs):
        calls.append(kwargs)
        return {
            "has_plan": True,
            "rule_version": "plan_actual_match_v1",
            "base_checkpoint_id": checkpoint["id"],
            "rows": [
                {
                    "session_id": template["session_id"],
                    "target_key": f"session:{template['session_id']}",
                    "date": yesterday.isoformat(),
                    "name": "Quality bike",
                    "role": "quality",
                    "sport": "bike",
                    "tss": 60.0,
                    "duration_minutes": 60,
                    "match_status": "matched",
                    "match_method": "date_sport_heuristic",
                    "confidence": 0.75,
                    "adherence": "exact",
                    "actual_activity_ids": ["ride-yesterday"],
                    "actual_activities": [
                        {
                            "activity_id": "ride-yesterday",
                            "date": yesterday.isoformat(),
                            "started_at_utc": f"{yesterday.isoformat()}T08:00:00Z",
                            "duration_minutes": 60,
                            "sport": "bike",
                            "tss": 60.0,
                        }
                    ],
                    "actual_total_tss": 60.0,
                    "actual_duration_minutes": 60.0,
                    "actual_sport": "bike",
                    "actual_role": "quality",
                    "evidence": ["stable local match"],
                }
            ],
            "unplanned_activities": [],
            "data_quality": {},
        }

    monkeypatch.setattr(snapshot_module, "reconciliation_at", fake_reconciliation)
    _patch_report(monkeypatch, _report(today))
    _patch_snapshot(monkeypatch, _snapshot())

    payload = today_view(db=db)

    assert len(calls) == 1
    assert calls[0]["include_provider"] is False
    assert payload["feedback"]["status"] == "available"
    assert payload["feedback"]["primary"]["session_id"] == template["session_id"]
    assert payload["feedback"]["primary"]["state"] == "ready"
    assert db.get_database_stats()["session_feedback"] == 0


def test_today_feedback_failure_is_fail_open(tmp_path, monkeypatch) -> None:
    from api import today_snapshot as snapshot_module
    from api.routers.today import today_view

    today = date(2026, 7, 13)
    db = Database(str(tmp_path / "feedback-fail-open.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today, target_role="easy")))
    _patch_report(monkeypatch, _report(today))
    _patch_snapshot(monkeypatch, _snapshot())
    monkeypatch.setattr(
        snapshot_module,
        "feedback_from_today_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("feedback offline")),
    )

    payload = today_view(db=db)

    assert payload["state"] == "silence"
    assert payload["primary_action"]["kind"] == "follow_plan"
    assert payload["feedback"]["status"] == "unavailable"
    assert "feedback offline" in payload["feedback"]["reason"]


def test_today_route_is_wired_into_app() -> None:
    """FastAPI этой версии включает роутеры лениво (_IncludedRouter без .path),
    поэтому проверяем резолвинг по имени эндпоинта."""
    from api.main import app

    assert app.url_path_for("today_view") == "/api/today"


# --- #397: подсказка синхронизировать устройство после recovery_replan ------


def test_device_sync_hint_fires_on_today_recovery_replan() -> None:
    from api.today_snapshot import _device_sync_hint

    today = "2026-08-08"
    checkpoint = {
        "id": 77,
        "checkpoint_source": "recovery_replan",
        "created_at": "2026-08-08T06:41:49",
    }
    deliveries = [
        {
            "checkpoint_id": 77,
            "dates": ["2026-08-08"],
            "status": "success",
            "created_at": "2026-08-08T06:41:10",
        }
    ]

    hint = _device_sync_hint(checkpoint, today, deliveries)

    assert hint == {
        "reason": "recovery_replan",
        "at": "2026-08-08T06:41:49",
        "delivered_at": "2026-08-08T06:41:10",
    }


def test_device_sync_hint_silent_without_today_replan() -> None:
    from api.today_snapshot import _device_sync_hint

    today = "2026-08-08"
    deliveries = [
        {
            "checkpoint_id": 77,
            "dates": ["2026-08-08"],
            "status": "success",
            "created_at": "2026-08-08T06:41:10",
        }
    ]
    replan = {
        "id": 77,
        "checkpoint_source": "recovery_replan",
        "created_at": "2026-08-08T06:41:49",
    }

    assert (
        _device_sync_hint(
            {
                "id": 77,
                "checkpoint_source": "initial_plan",
                "created_at": "2026-08-08T06:00:00",
            },
            today,
            deliveries,
        )
        is None
    )
    assert (
        _device_sync_hint(
            {
                "id": 77,
                "checkpoint_source": "recovery_replan",
                "created_at": "2026-08-07T06:00:00",
            },
            today,
            deliveries,
        )
        is None
    )
    # Без успешной доставки на сегодня — подсказки нет (P1).
    assert (
        _device_sync_hint(replan, today, [])
        is None
    )
    # Доставка на другую дату / от другого чекпоинта — не считается (P2).
    assert (
        _device_sync_hint(
            replan,
            today,
            [
                {
                    "checkpoint_id": 77,
                    "dates": ["2026-08-09"],
                    "status": "success",
                    "created_at": "2026-08-08T06:41:10",
                }
            ],
        )
        is None
    )
    assert (
        _device_sync_hint(
            replan,
            today,
            [
                {
                    "checkpoint_id": 78,
                    "dates": ["2026-08-08"],
                    "status": "success",
                    "created_at": "2026-08-08T06:41:10",
                }
            ],
        )
        is None
    )


def test_today_snapshot_carries_device_sync_hint_for_recovery_replan(tmp_path) -> None:
    import json as _json

    from api.today_snapshot import build_today_decision_snapshot

    today = date.today()  # created_at чекпоинта = реальная дата (CURRENT_TIMESTAMP)
    goal_plan = _goal_plan(today)
    goal_plan["checkpoint_source"] = "recovery_replan"
    db = Database(str(tmp_path / "sync-hint.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))
    # Успешная доставка этого же дня из чекпоинта 1 (первый сохранённый).
    today_iso = today.isoformat()
    conn = sqlite3.connect(db.db_path)
    try:
        conn.execute(
            """INSERT INTO coach_proposals
               (date, action, status, params_json, preview_json, result_json, created_at)
               VALUES (?, 'recovery_replan', 'approved', '{}', '{}', ?, '2026-08-08T06:41:10')""",
            (
                today_iso,
                _json.dumps(
                    {
                        "delivery": {
                            "status": "success",
                            "checkpoint_id": 1,
                            "dates": [today_iso],
                        }
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    payload = build_today_decision_snapshot(db, today=today)

    hint = payload.get("device_sync_hint")
    assert hint is not None
    assert hint["reason"] == "recovery_replan"
    assert hint["at"][:10] == today_iso

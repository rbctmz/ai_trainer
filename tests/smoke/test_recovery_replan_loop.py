"""Behavior contract for Issue F: auditable RecoveryReplanLoop."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import sqlite3
from threading import Barrier

import pytest
from fastapi import HTTPException

from api.recovery_replan_loop import run_recovery_replan_loop
from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from models.recovery_replan import build_recovery_replan_variant


def _goal_plan(today: date, *, conflict_days_until: int = 6) -> dict:
    monday = today - timedelta(days=today.weekday())
    target_date = today + timedelta(days=conflict_days_until)
    daily_plan = []
    templates = []
    for index in range(21):
        session_date = monday + timedelta(days=index)
        is_target = session_date == target_date
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


def _conflict_report(
    today: date,
    *,
    days_until: int = 6,
    status: str = "low",
    severity: str = "high",
) -> dict:
    session_date = today + timedelta(days=days_until)
    session = {
        "date": session_date.isoformat(),
        "days_until": days_until,
        "role": "quality",
        "tss": 60,
        "name": "Качество • вело",
        "sport_label": "вело",
        "phase": "Build",
    }
    return {
        "as_of": today.isoformat(),
        "horizon_days": 7,
        "base_horizon_days": 3,
        "lookahead_policy": "base_plus_nearest_quality",
        "horizon_extended_for_quality": True,
        "quality_lookahead_session": dict(session),
        "readiness": {"score": 35.0, "status": status, "confidence": 0.8},
        "sessions_evaluated": [dict(session)],
        "conflicts": [
            {
                "date": session["date"],
                "days_until": days_until,
                "severity": severity,
                "kind": f"{status}_readiness_quality_session",
                "session": {
                    "name": session["name"],
                    "role": "quality",
                    "tss": 60,
                    "sport_label": "вело",
                },
                "evidence": [
                    "Готовность 35/100 (low): HRV -18% к базе",
                    f"Через {days_until} дн.: Качество • вело, 60 TSS",
                ],
            }
        ],
        "silence": False,
        "data_gap": False,
        "reason": "Готовность low расходится с качественной сессией.",
    }


def _silence_report(today: date, *, data_gap: bool = False) -> dict:
    return {
        "as_of": today.isoformat(),
        "horizon_days": 3,
        "base_horizon_days": 3,
        "lookahead_policy": "base_plus_nearest_quality",
        "horizon_extended_for_quality": False,
        "quality_lookahead_session": None,
        "readiness": {
            "score": None if data_gap else 72.0,
            "status": "unknown" if data_gap else "ready",
            "confidence": 0.0 if data_gap else 0.8,
        },
        "sessions_evaluated": [],
        "conflicts": [],
        "silence": True,
        "data_gap": data_gap,
        "reason": "Недостаточно данных." if data_gap else "План и состояние согласны.",
    }


def _save_plan(db: Database, goal_plan: dict) -> dict:
    return db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))


def test_recovery_variant_targets_absolute_date_beyond_old_ten_row_cap() -> None:
    today = date(2026, 7, 12)  # Sunday: day +6 is plan index 12 from Monday.
    goal_plan = _goal_plan(today, conflict_days_until=6)

    variant = build_recovery_replan_variant(
        goal_plan,
        _conflict_report(today, days_until=6),
        today=today,
    )

    assert variant is not None
    assert variant["selected_conflict"]["severity"] == "high"
    assert variant["horizon_days"] == 13
    assert variant["recommended_session"]["date"] == (today + timedelta(days=6)).isoformat()
    assert variant["recommended_session"]["role"] == "recovery"
    assert variant["recommended_session"]["tss"] == 25
    assert variant["recommended_session"]["delta_tss"] == -35
    assert [option["key"] for option in variant["options"]] == ["keep", "recommended"]
    assert variant["post_edit_strategy"] == "protect_recovery"


def test_medium_quality_conflict_downgrades_to_easy_without_llm() -> None:
    today = date(2026, 7, 10)
    variant = build_recovery_replan_variant(
        _goal_plan(today, conflict_days_until=4),
        _conflict_report(
            today,
            days_until=4,
            status="limited",
            severity="medium",
        ),
        today=today,
    )

    assert variant is not None
    assert variant["recommended_session"]["role"] == "easy"
    assert variant["recommended_session"]["tss"] == 35
    assert variant["recommended_session"]["delta_tss"] == -25


def test_recovery_variant_never_targets_race_protected_date() -> None:
    today = date(2026, 7, 10)
    target_date = today + timedelta(days=4)
    goal_plan = _goal_plan(today, conflict_days_until=4)
    goal_plan["protected_dates"] = [target_date.isoformat()]
    target_index = next(
        index for index, row in enumerate(goal_plan["daily_plan"]) if row[0].date() == target_date
    )
    dt, _total, _parts = goal_plan["daily_plan"][target_index]
    goal_plan["daily_plan"][target_index] = (dt, 0.0, {"bike": 0.0})
    goal_plan["session_templates"][target_index]["protected_by_event"] = True

    variant = build_recovery_replan_variant(
        goal_plan,
        _conflict_report(today, days_until=4),
        today=today,
    )

    assert variant is None


def test_database_recovery_decision_and_proposal_source_are_idempotent(tmp_path) -> None:
    db = Database(str(tmp_path / "recovery-log.db"))
    report = _silence_report(date(2026, 7, 10))

    first = db.save_recovery_decision(
        fingerprint="stable-fingerprint",
        outcome="silence",
        reason=report["reason"],
        report=report,
        plan_checkpoint_id=41,
        date="2026-07-10T08:00:00",
    )
    second = db.save_recovery_decision(
        fingerprint="stable-fingerprint",
        outcome="silence",
        reason="duplicate call",
        report=report,
        plan_checkpoint_id=41,
        date="2026-07-10T08:01:00",
    )

    assert first["created"] is True
    assert second["created"] is False
    assert second["decision"]["id"] == first["decision"]["id"]
    assert len(db.get_recovery_decisions(days=36500)) == 1

    proposal_1 = db.save_coach_proposal(
        action="recovery_replan",
        params={"base_checkpoint_id": 41, "draft_rows": []},
        preview={"reason": "conflict"},
        source="recovery_replan",
        source_key="stable-fingerprint",
    )
    proposal_2 = db.save_coach_proposal(
        action="recovery_replan",
        params={"base_checkpoint_id": 41, "draft_rows": []},
        preview={"reason": "duplicate"},
        source="recovery_replan",
        source_key="stable-fingerprint",
    )

    assert proposal_2["id"] == proposal_1["id"]
    assert proposal_2["preview"]["reason"] == "conflict"

    claimed = db.transition_coach_proposal_status(proposal_1["id"], "pending", "applying")
    duplicate_claim = db.transition_coach_proposal_status(
        proposal_1["id"], "pending", "applying"
    )
    assert claimed["status"] == "applying"
    assert duplicate_claim is None
    assert db.transition_coach_proposal_status(
        proposal_1["id"], "applying", "pending"
    )["status"] == "pending"


def test_database_reuses_active_proposal_key_until_terminal_status(tmp_path) -> None:
    db = Database(str(tmp_path / "active-proposal-key.db"))
    shared = {
        "action": "recovery_replan",
        "params": {"base_checkpoint_id": 41, "draft_rows": []},
        "preview": {"reason": "first snapshot"},
        "source": "recovery_replan",
        "active_key": "athlete-day:checkpoint:target-session",
    }

    pending = db.save_coach_proposal(source_key="fingerprint-1", **shared)
    reused_pending = db.save_coach_proposal(
        source_key="fingerprint-2",
        **{**shared, "preview": {"reason": "second snapshot"}},
    )

    assert reused_pending["id"] == pending["id"]
    assert reused_pending["source_key"] == "fingerprint-1"
    assert reused_pending["active_key"] == shared["active_key"]
    assert reused_pending["preview"]["reason"] == "first snapshot"

    applying = db.transition_coach_proposal_status(pending["id"], "pending", "applying")
    reused_applying = db.save_coach_proposal(source_key="fingerprint-3", **shared)

    assert applying["status"] == "applying"
    assert reused_applying["id"] == pending["id"]
    assert reused_applying["status"] == "applying"

    db.update_coach_proposal_status(pending["id"], "approved")
    replacement = db.save_coach_proposal(source_key="fingerprint-4", **shared)

    assert replacement["id"] != pending["id"]
    assert replacement["status"] == "pending"
    assert len(db.get_coach_proposals(days=36500)) == 2


def test_database_serializes_concurrent_active_proposal_creation(tmp_path) -> None:
    db = Database(str(tmp_path / "concurrent-active-key.db"))
    barrier = Barrier(2)

    def save_proposal(sequence: int) -> dict:
        barrier.wait()
        return db.save_coach_proposal(
            action="recovery_replan",
            params={"base_checkpoint_id": 41, "draft_rows": []},
            preview={"sequence": sequence},
            source="recovery_replan",
            source_key=f"concurrent-fingerprint-{sequence}",
            active_key="concurrent-athlete-day:checkpoint:target-session",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        proposals = list(executor.map(save_proposal, (1, 2)))

    assert proposals[0]["id"] == proposals[1]["id"]
    assert len(db.get_coach_proposals(days=36500, status="pending")) == 1


def test_database_migrates_legacy_proposals_with_nullable_active_key(tmp_path) -> None:
    db_path = tmp_path / "legacy-proposals.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE coach_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                params_json TEXT NOT NULL,
                preview_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                chat_id TEXT,
                message_id TEXT,
                resolved_at TEXT,
                source TEXT,
                source_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO coach_proposals
                (date, action, status, params_json, preview_json)
            VALUES ('2026-07-10', 'build_plan', 'pending', '{}', '{}')
            """
        )

    db = Database(str(db_path))

    legacy = db.get_coach_proposals(days=36500)
    assert legacy[0]["active_key"] is None
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(coach_proposals)")}
        index_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'idx_coach_proposals_active_key'"
        ).fetchone()[0]
    assert "active_key" in columns
    assert "status IN ('pending', 'applying')" in index_sql


@pytest.mark.parametrize(
    ("data_gap", "expected_outcome"),
    [(False, "silence"), (True, "data_gap")],
)
def test_loop_logs_non_intervention_once_without_proposal(
    tmp_path,
    monkeypatch,
    data_gap: bool,
    expected_outcome: str,
) -> None:
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 10)
    report = _silence_report(today, data_gap=data_gap)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db = Database(str(tmp_path / f"{expected_outcome}.db"))

    first = run_recovery_replan_loop(db, today=today)
    second = run_recovery_replan_loop(db, today=today)

    assert first["outcome"] == expected_outcome
    assert second["decision"]["id"] == first["decision"]["id"]
    assert first["proposal"] is None
    assert db.get_coach_proposals(days=36500) == []
    assert len(db.get_recovery_decisions(days=36500)) == 1


def test_loop_creates_one_recovery_proposal_and_exposes_it_in_decisions_api(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module
    from api.routers.decisions import list_decisions

    today = date(2026, 7, 10)
    report = _conflict_report(today, days_until=4)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db = Database(str(tmp_path / "loop-conflict.db"))
    checkpoint = _save_plan(db, _goal_plan(today, conflict_days_until=4))

    first = run_recovery_replan_loop(db, today=today)
    second = run_recovery_replan_loop(db, today=today)

    assert first["outcome"] == "conflict"
    assert first["proposal"]["action"] == "recovery_replan"
    assert first["proposal"]["params"]["base_checkpoint_id"] == checkpoint["id"]
    assert first["proposal"]["preview"]["options"][0]["key"] == "keep"
    assert second["proposal"]["id"] == first["proposal"]["id"]
    assert len(db.get_coach_proposals(days=36500)) == 1
    assert len(db.get_recovery_decisions(days=36500)) == 1

    payload = list_decisions(days=36500, db=db)
    assert payload["recovery_count"] == 1
    recovery = payload["recovery_days"][0]["recovery_decisions"][0]
    assert recovery["outcome"] == "conflict"
    assert recovery["proposal_id"] == first["proposal"]["id"]
    assert recovery["report"]["conflicts"][0]["severity"] == "high"


def test_loop_keeps_intraday_decisions_but_reuses_target_session_proposal(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 10)
    first_report = _conflict_report(today, days_until=4)
    second_report = _conflict_report(today, days_until=4)
    second_report["readiness"] = {
        **second_report["readiness"],
        "score": 36.0,
    }
    second_report["conflicts"][0]["evidence"][0] = (
        "Готовность 36/100 (low): HRV -17% к базе"
    )
    reports = iter((first_report, second_report))
    monkeypatch.setattr(
        loop_module,
        "build_readiness_conflict_report",
        lambda _db: next(reports),
    )
    db = Database(str(tmp_path / "intraday-dedup.db"))
    _save_plan(db, _goal_plan(today, conflict_days_until=4))

    first = run_recovery_replan_loop(db, today=today)
    second = run_recovery_replan_loop(db, today=today)

    assert second["decision"]["id"] != first["decision"]["id"]
    assert second["decision"]["proposal_id"] == first["proposal"]["id"]
    assert second["proposal"]["id"] == first["proposal"]["id"]
    assert second["proposal"]["active_key"] == first["proposal"]["active_key"]
    assert len(db.get_recovery_decisions(days=36500)) == 2
    assert len(db.get_coach_proposals(days=36500)) == 1


def test_recovery_proposal_reject_approve_and_append_only_rollback(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module
    from api.routers import decisions as decisions_router
    from api.routers.decisions import approve_proposal, reject_proposal, rollback_proposal

    today = date(2026, 7, 10)
    report = _conflict_report(today, days_until=4)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    delivery_calls = []

    def fake_delivery(_db, *, dates, source, **_kwargs):
        delivery_calls.append({"dates": list(dates), "source": source})
        return {
            "status": "failed",
            "retryable": True,
            "error": "provider unavailable",
            "dates": list(dates),
        }

    monkeypatch.setattr(
        decisions_router,
        "safe_deliver_active_plan",
        fake_delivery,
        raising=False,
    )

    reject_db = Database(str(tmp_path / "reject.db"))
    reject_base = _save_plan(reject_db, _goal_plan(today, conflict_days_until=4))
    rejected = run_recovery_replan_loop(reject_db, today=today)["proposal"]
    reject_payload = reject_proposal(rejected["id"], db=reject_db)
    assert reject_payload["proposal"]["status"] == "rejected"
    assert reject_db.get_latest_planning_checkpoint()["id"] == reject_base["id"]

    db = Database(str(tmp_path / "approve-rollback.db"))
    base = _save_plan(db, _goal_plan(today, conflict_days_until=4))
    proposal = run_recovery_replan_loop(db, today=today)["proposal"]
    approved = approve_proposal(proposal["id"], db=db)

    assert approved["proposal"]["status"] == "approved"
    assert approved["result"]["rollback_checkpoint_id"] == base["id"]
    assert approved["result"]["affected_dates"] == [
        (today + timedelta(days=4)).isoformat()
    ]
    assert approved["result"]["delivery"]["status"] == "failed"
    applied = db.get_latest_planning_checkpoint()
    assert applied["id"] == int(approved["result"]["plan_id"])
    assert applied["checkpoint_source"] == "recovery_replan"
    assert applied["checkpoint_parent_id"] == base["id"]
    target_date = (today + timedelta(days=4)).isoformat()
    applied_template = next(
        row
        for row in applied["goal_plan_snapshot"]["session_templates"]
        if row["date"] == target_date
    )
    assert applied_template["session_role"] == "recovery"

    rolled_back = rollback_proposal(proposal["id"], db=db)
    assert rolled_back["proposal"]["status"] == "rolled_back"
    assert delivery_calls == [
        {
            "dates": [(today + timedelta(days=4)).isoformat()],
            "source": "recovery_approve",
        },
        {
            "dates": [(today + timedelta(days=4)).isoformat()],
            "source": "recovery_rollback",
        },
    ]
    restored = db.get_latest_planning_checkpoint()
    assert restored["id"] > applied["id"]
    assert restored["checkpoint_source"] == "restore_version"
    assert restored["checkpoint_parent_id"] == applied["id"]
    assert restored["checkpoint_restored_from_checkpoint_id"] == base["id"]
    restored_template = next(
        row
        for row in restored["goal_plan_snapshot"]["session_templates"]
        if row["date"] == target_date
    )
    assert restored_template["session_role"] == "quality"


def test_recovery_approve_and_rollback_refuse_stale_active_plan(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module
    from api.routers.decisions import approve_proposal, rollback_proposal

    today = date(2026, 7, 10)
    report = _conflict_report(today, days_until=4)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)

    stale_approve_db = Database(str(tmp_path / "stale-approve.db"))
    _save_plan(stale_approve_db, _goal_plan(today, conflict_days_until=4))
    stale_proposal = run_recovery_replan_loop(stale_approve_db, today=today)["proposal"]
    _save_plan(stale_approve_db, _goal_plan(today, conflict_days_until=3))

    with pytest.raises(HTTPException) as approve_error:
        approve_proposal(stale_proposal["id"], db=stale_approve_db)
    assert approve_error.value.status_code == 409
    assert stale_approve_db.get_coach_proposal(stale_proposal["id"])["status"] == "failed"

    stale_rollback_db = Database(str(tmp_path / "stale-rollback.db"))
    _save_plan(stale_rollback_db, _goal_plan(today, conflict_days_until=4))
    proposal = run_recovery_replan_loop(stale_rollback_db, today=today)["proposal"]
    approved = approve_proposal(proposal["id"], db=stale_rollback_db)
    applied_id = int(approved["result"]["plan_id"])
    _save_plan(stale_rollback_db, _goal_plan(today, conflict_days_until=2))

    with pytest.raises(HTTPException) as rollback_error:
        rollback_proposal(proposal["id"], db=stale_rollback_db)
    assert rollback_error.value.status_code == 409
    assert stale_rollback_db.get_latest_planning_checkpoint()["id"] != applied_id
    assert stale_rollback_db.get_coach_proposal(proposal["id"])["status"] == "approved"

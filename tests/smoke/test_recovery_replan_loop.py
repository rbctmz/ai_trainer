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


def test_legacy_recovery_rollback_without_affected_dates_skips_delivery(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module
    from api.routers.decisions import approve_proposal, rollback_proposal

    today = date(2026, 7, 10)
    report = _conflict_report(today, days_until=4)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db = Database(str(tmp_path / "legacy-empty-affected-dates.db"))
    _save_plan(db, _goal_plan(today, conflict_days_until=4))
    proposal = run_recovery_replan_loop(db, today=today)["proposal"]
    approved = approve_proposal(proposal["id"], db=db)
    legacy_result = dict(approved["result"])
    legacy_result.pop("affected_dates", None)
    db.update_coach_proposal_status(
        proposal["id"],
        "approved",
        result=legacy_result,
    )

    rolled_back = rollback_proposal(proposal["id"], db=db)

    assert rolled_back["proposal"]["status"] == "rolled_back"
    assert rolled_back["result"]["affected_dates"] == []
    assert rolled_back["result"]["delivery"]["status"] == "skipped"
    assert rolled_back["result"]["delivery"]["failed_count"] == 0
    assert rolled_back["result"]["delivery"]["retryable"] is False


# ---------------------------------------------------------------------------
# M3 RED — three-variant decision contract in the loop (Issue #209).
#
# Pins, before the loop composes `variants = [keep, downgrade_today,
# transfer_1_3d?]` per docs/recovery_transfer_execplan.md Design/M3:
#
# - a safe D+1..D+3 date yields all three typed variants, keyed by "kind",
#   and `transfer_1_3d` is the recommended one when eligible (it preserves
#   the key session instead of downgrading it in place);
# - no safe date omits `transfer_1_3d` but the preview still exposes every
#   candidate's exact rejection reasons via `transfer_candidates`, and
#   `downgrade_today` stays the recommended fallback;
# - the loop stays idempotent per readiness/proposal fingerprint even though
#   the three variants are recomputed on every run (byte-stable recompute,
#   no extra proposal rows);
# - one current proposal per conflicting session survives repeated reruns
#   with a shifted readiness score, and its preview keeps refreshing with
#   the up-to-date `transfer_1_3d` variant;
# - a conflict whose claimed role no longer matches the active plan's role
#   at that date (a stale readiness snapshot racing a plan that already
#   moved on) fails closed on the transfer variant only — keep/
#   downgrade_today are unaffected and the loop never raises;
# - a proposal row written before M3 shipped (preview without "variants")
#   is reused by active_key, not duplicated, and its preview is upgraded
#   in place once M3 recomputes it.
#
# `_goal_plan(today, conflict_days_until=1)` puts the conflicting quality
# session on a Tuesday when `today` is the Monday start of the plan, so
# D+1..D+3 (Wed/Thu/Fri) stay inside the source ISO week (no
# `cross_week_boundary`) with easy, non-hard neighbours (no
# `hard_collision`/`recovery_spacing`) and plenty of TSS/duration headroom.


def _transfer_ready_goal_plan(today: date, *, days_until: int = 1) -> dict:
    return _goal_plan(today, conflict_days_until=days_until)


def _variant_kinds(proposal: dict) -> list:
    return [str(v.get("kind")) for v in proposal["preview"]["variants"]]


def test_loop_offers_transfer_variant_alongside_keep_and_downgrade_when_safe_date_exists(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 13)  # Monday
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db = Database(str(tmp_path / "transfer-safe.db"))
    _save_plan(db, _transfer_ready_goal_plan(today, days_until=1))

    first = run_recovery_replan_loop(db, today=today)

    assert first["outcome"] == "conflict"
    assert _variant_kinds(first["proposal"]) == ["keep", "downgrade_today", "transfer_1_3d"]

    transfer = next(
        v for v in first["proposal"]["preview"]["variants"] if v["kind"] == "transfer_1_3d"
    )
    conflict_date = today + timedelta(days=1)
    assert transfer["target_date"] == (conflict_date + timedelta(days=1)).isoformat()
    assert transfer["new_session"]["sport"] == "bike"
    assert transfer["new_session"]["session_role"] == "quality"
    assert float(transfer["new_session"]["total_tss"]) == 60.0
    assert transfer["new_session"]["replaces_session_id"]
    assert transfer["new_session"]["transfer_group_id"]
    assert transfer["rule_version"] == "recovery-transfer-v1"

    recommended = [
        v["kind"] for v in first["proposal"]["preview"]["variants"] if v.get("recommended")
    ]
    assert recommended == ["transfer_1_3d"]


def test_loop_omits_transfer_variant_and_exposes_candidate_rejections_when_no_safe_date(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 13)
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    goal_plan = _transfer_ready_goal_plan(today, days_until=1)
    conflict_date = today + timedelta(days=1)
    goal_plan["protected_dates"] = [
        (conflict_date + timedelta(days=offset)).isoformat() for offset in (1, 2, 3)
    ]
    db = Database(str(tmp_path / "transfer-blocked.db"))
    _save_plan(db, goal_plan)

    first = run_recovery_replan_loop(db, today=today)

    assert first["outcome"] == "conflict"
    assert _variant_kinds(first["proposal"]) == ["keep", "downgrade_today"]
    candidates = first["proposal"]["preview"]["transfer_candidates"]
    assert len(candidates) == 3
    assert all(row["eligible"] is False for row in candidates)
    assert all(row["rejected_reasons"] == ["protected"] for row in candidates)
    recommended = [
        v["kind"] for v in first["proposal"]["preview"]["variants"] if v.get("recommended")
    ]
    assert recommended == ["downgrade_today"]


def test_loop_transfer_variant_is_idempotent_across_repeated_runs(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 13)
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db = Database(str(tmp_path / "transfer-idempotent.db"))
    _save_plan(db, _transfer_ready_goal_plan(today, days_until=1))

    first = run_recovery_replan_loop(db, today=today)
    second = run_recovery_replan_loop(db, today=today)

    assert second["proposal"]["id"] == first["proposal"]["id"]
    assert second["proposal"]["preview"]["variants"] == first["proposal"]["preview"]["variants"]
    assert len(db.get_coach_proposals(days=36500)) == 1


def test_loop_keeps_single_current_proposal_when_readiness_shifts_but_target_session_is_unchanged(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 13)
    first_report = _conflict_report(today, days_until=1)
    second_report = _conflict_report(today, days_until=1)
    second_report["readiness"] = {**second_report["readiness"], "score": 36.0}
    second_report["conflicts"][0]["evidence"][0] = (
        "Готовность 36/100 (low): HRV -17% к базе"
    )
    reports = iter((first_report, second_report))
    monkeypatch.setattr(
        loop_module,
        "build_readiness_conflict_report",
        lambda _db: next(reports),
    )
    db = Database(str(tmp_path / "transfer-single-proposal.db"))
    _save_plan(db, _transfer_ready_goal_plan(today, days_until=1))

    first = run_recovery_replan_loop(db, today=today)
    second = run_recovery_replan_loop(db, today=today)

    assert second["decision"]["id"] != first["decision"]["id"]
    assert second["proposal"]["id"] == first["proposal"]["id"]
    assert len(db.get_coach_proposals(days=36500)) == 1
    assert len(db.get_recovery_decisions(days=36500)) == 2
    assert "transfer_1_3d" in _variant_kinds(second["proposal"])


def test_loop_fails_closed_on_transfer_when_conflict_session_role_has_drifted(
    tmp_path,
    monkeypatch,
) -> None:
    """Readiness report claims a quality session at D+1, but the active plan
    already changed that day's role to easy (e.g. a prior downgrade already
    applied). The transfer variant must fail closed instead of moving
    whatever now sits on that date; keep/downgrade_today stay unaffected."""
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 13)
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    goal_plan = _transfer_ready_goal_plan(today, days_until=1)
    conflict_date = today + timedelta(days=1)
    target_index = next(
        index
        for index, row in enumerate(goal_plan["daily_plan"])
        if row[0].date() == conflict_date
    )
    dt, _total, _parts = goal_plan["daily_plan"][target_index]
    goal_plan["daily_plan"][target_index] = (dt, 20.0, {"run": 20.0})
    goal_plan["session_templates"][target_index].update(
        {
            "session_role": "easy",
            "sport": "run",
            "sport_label": "бег",
            "session_focus": "Лёгкая • бег",
            "duration_minutes": 30,
        }
    )
    db = Database(str(tmp_path / "transfer-role-drift.db"))
    _save_plan(db, goal_plan)

    first = run_recovery_replan_loop(db, today=today)

    assert first["outcome"] == "conflict"
    assert _variant_kinds(first["proposal"]) == ["keep", "downgrade_today"]


def test_loop_upgrades_legacy_pending_proposal_preview_with_variants_on_reuse(
    tmp_path,
    monkeypatch,
) -> None:
    """A proposal row written by pre-M3 code (preview without "variants")
    must be reused by active_key, not duplicated, and its preview upgraded
    in place — the additive-fields back-compat promise from ASR-MOD-3."""
    import json

    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 13)
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db_path = tmp_path / "transfer-legacy-upgrade.db"
    db = Database(str(db_path))
    _save_plan(db, _transfer_ready_goal_plan(today, days_until=1))

    seeded = run_recovery_replan_loop(db, today=today)["proposal"]
    legacy_preview = {
        key: value
        for key, value in seeded["preview"].items()
        if key not in ("variants", "transfer_candidates")
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE coach_proposals SET preview_json = ? WHERE id = ?",
            (json.dumps(legacy_preview, ensure_ascii=False), seeded["id"]),
        )
        conn.commit()
    assert "variants" not in db.get_coach_proposal(seeded["id"])["preview"]

    second = run_recovery_replan_loop(db, today=today)

    assert second["proposal"]["id"] == seeded["id"]
    assert "variants" in second["proposal"]["preview"]
    assert "transfer_1_3d" in _variant_kinds(second["proposal"])


# ---------------------------------------------------------------------------
# M3 checker round — RED-only checkpoint for two blockers pinned on top of
# the accepted M3 GREEN (e4fd032):
# https://github.com/rbctmz/ai_trainer/pull/210#issuecomment-5010705155
#
# 1. `actual_hard_dates` never reaches the production loop's calls to
#    `rank_transfer_candidates`/`build_transfer_variant` — the pure ranker
#    already honours it (models/recovery_transfer.py,
#    test_unplanned_actual_hard_load_blocks_adjacent_candidate), but
#    `api/recovery_replan_loop.py` always calls both with the default
#    `actual_hard_dates=None`, so a real already-executed hard activity next
#    to a D+1..D+3 candidate is silently ignored end to end.
#
# 2. `_resolve_transfer_session_id` matches the readiness conflict's claimed
#    `(date, role)` against the active plan by role ONLY — it ignores sport,
#    and picks the FIRST same-role session unconditionally. A sport-only
#    drift (the plan's quality slot on that date changed discipline) or a
#    day carrying two same-role sessions (ambiguous — the conflict has no
#    `session_id` to disambiguate with) both currently resolve to whatever
#    session happens to be first, instead of failing closed the way the
#    existing role-drift gate already does for a full role mismatch.


def test_loop_passes_executed_hard_activity_dates_into_transfer_ranking(
    tmp_path,
    monkeypatch,
) -> None:
    """A hard unplanned ride already logged on the SOURCE conflict date must
    still block an adjacent D+1..D+3 candidate via `recovery_spacing`,
    exactly as the pure ranker's own unit test proves
    (test_unplanned_actual_hard_load_blocks_adjacent_candidate). The
    production loop must read this already-persisted local evidence
    (`db.save_activities`, no provider) and pass the same `actual_hard_dates`
    into both `rank_transfer_candidates` and `build_transfer_variant`."""
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 13)  # Monday
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db = Database(str(tmp_path / "transfer-actual-hard-load.db"))
    _save_plan(db, _transfer_ready_goal_plan(today, days_until=1))
    conflict_date = today + timedelta(days=1)  # 2026-07-14, Tuesday — source date
    db.save_activities(
        [
            {
                "activity_id": "unplanned-hard-ride",
                "date": conflict_date.isoformat(),
                "sport": "cycling",
                "duration_minutes": 150,
                "distance_km": 60.0,
                "tss": 95.0,
            }
        ]
    )

    first = run_recovery_replan_loop(db, today=today)

    assert first["outcome"] == "conflict"
    blocked_date = (conflict_date + timedelta(days=1)).isoformat()  # 2026-07-15
    safe_date = (conflict_date + timedelta(days=2)).isoformat()  # 2026-07-16
    candidates = {
        row["date"]: row for row in first["proposal"]["preview"]["transfer_candidates"]
    }
    assert candidates[blocked_date]["eligible"] is False
    assert candidates[blocked_date]["rejected_reasons"] == ["recovery_spacing"]
    assert candidates[safe_date]["eligible"] is True

    transfer = next(
        (v for v in first["proposal"]["preview"]["variants"] if v["kind"] == "transfer_1_3d"),
        None,
    )
    assert transfer is not None, "actual hard load must not remove the transfer offer entirely"
    assert transfer["target_date"] == safe_date


def test_loop_fails_closed_on_transfer_when_conflict_session_sport_has_drifted(
    tmp_path,
    monkeypatch,
) -> None:
    """Readiness report claims a quality BIKE session at D+1 ('Качество •
    vело'), but the active plan's session at that date and role has since
    become a quality RUN session (e.g. a sport swap already applied since
    the report was built). `_resolve_transfer_session_id` matches on role
    only, so it currently accepts this same-role-different-sport session and
    happily builds a transfer for the wrong workout. This must fail closed
    on `transfer_1_3d` only, exactly like the existing full role-drift gate;
    keep/downgrade_today stay unaffected."""
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 13)
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    goal_plan = _transfer_ready_goal_plan(today, days_until=1)
    conflict_date = today + timedelta(days=1)
    target_index = next(
        index
        for index, row in enumerate(goal_plan["daily_plan"])
        if row[0].date() == conflict_date
    )
    dt, total, _parts = goal_plan["daily_plan"][target_index]
    goal_plan["daily_plan"][target_index] = (dt, total, {"run": total})
    goal_plan["session_templates"][target_index].update(
        {
            "sport": "run",
            "sport_label": "бег",
            "session_focus": "Качество • бег",
        }
    )
    db = Database(str(tmp_path / "transfer-sport-drift.db"))
    _save_plan(db, goal_plan)

    first = run_recovery_replan_loop(db, today=today)

    assert first["outcome"] == "conflict"
    assert _variant_kinds(first["proposal"]) == ["keep", "downgrade_today"]


def test_loop_fails_closed_on_transfer_when_two_identical_sessions_share_conflicting_role_and_date(
    tmp_path,
    monkeypatch,
) -> None:
    """The conflict date carries two BYTE-IDENTICAL quality-bike sessions
    (a legitimate twin day, per the M2 twin-identity matrix). The readiness
    report never carries a `session_id` (M3 design) — only `(date, role)` —
    so nothing in the conflict can tell which of the two twins it actually
    means, even once sport/name/tss are also matched. Today
    `_resolve_transfer_session_id` grabs the FIRST same-role session
    unconditionally and builds a transfer for it anyway: an arbitrary,
    unauditable choice. A genuinely ambiguous same-role/same-date match must
    fail closed on `transfer_1_3d` only; keep/downgrade_today stay
    unaffected."""
    from api import recovery_replan_loop as loop_module

    today = date(2026, 7, 13)
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    goal_plan = _transfer_ready_goal_plan(today, days_until=1)
    conflict_date = today + timedelta(days=1)
    target_index = next(
        index
        for index, row in enumerate(goal_plan["daily_plan"])
        if row[0].date() == conflict_date
    )
    twin_session = {
        "sport": "bike",
        "sport_label": "вело",
        "session_role": "quality",
        "session_focus": "Качество • вело",
        "duration_minutes": 60,
        "total_tss": 60.0,
        "template_key": "build:quality:bike",
        "export_name": "Quality bike",
    }
    goal_plan["session_templates"][target_index]["sessions"] = [
        dict(twin_session),
        dict(twin_session),
    ]
    db = Database(str(tmp_path / "transfer-ambiguous-twins.db"))
    _save_plan(db, goal_plan)

    first = run_recovery_replan_loop(db, today=today)

    assert first["outcome"] == "conflict"
    assert _variant_kinds(first["proposal"]) == ["keep", "downgrade_today"]


# ---------------------------------------------------------------------------
# M4 RED — confirm/reject/rollback three-variant decision contract
# (Issue #209 M4 preflight, checker comment:
# https://github.com/rbctmz/ai_trainer/pull/210#issuecomment-5010778778)
#
# Pins, before `api/routers/decisions.py::approve_proposal` accepts an
# explicit `variant_kind` selection and routes `transfer_1_3d` confirmation
# through the shared `models/session_transfer.py::apply_session_transfer`
# primitive against the exact `base_checkpoint_id` (never the near-term
# editor, never an arbitrary client payload — see Decision Log):
#
# - approve accepts exactly one of the proposal's own saved variant kinds
#   (`keep` / `downgrade_today` / `transfer_1_3d`); an unknown or currently
#   unavailable kind fails closed with ZERO checkpoint mutation, and an
#   explicit `variant_kind=None` matches today's omitted-argument downgrade
#   contract byte-for-byte (legacy back-compat);
# - confirming `transfer_1_3d` creates exactly ONE new append-only
#   checkpoint with `checkpoint_source == "recovery_replan_transfer"`,
#   parented on the base, never touches the near-term editor, whose source
#   day loses the old session id and target day carries the SAME new
#   session id/lineage the preview promised with TSS preserved; the result
#   payload carries the selected kind, old/new session ids, both affected
#   dates (source AND target), and a rollback checkpoint id;
# - a stale active checkpoint refuses the transfer confirm with 409 and
#   appends no new checkpoint;
# - rollback of an applied transfer appends exactly ONE new restored
#   revision (never deletes history), the proposal becomes terminal
#   `rolled_back`, and the restored day structure/identity matches the
#   pre-transfer plan;
# - `safe_deliver_active_plan` (the provider boundary) is NEVER called for a
#   transfer confirm or a transfer rollback — Issue #209/M4 requires zero
#   provider calls anywhere on the transfer path;
# - a concurrent double-confirm of the SAME pending proposal is serialized
#   by the existing pending→applying claim and produces exactly one
#   checkpoint, never two.


def _transfer_preview(proposal: dict) -> dict:
    return next(v for v in proposal["preview"]["variants"] if v["kind"] == "transfer_1_3d")


def test_approve_recovery_transfer_variant_fails_closed_on_unknown_or_unavailable_kind(
    tmp_path,
    monkeypatch,
) -> None:
    """A conflict with no safe D+1..D+3 date never offers `transfer_1_3d` in
    its saved variants. Selecting it anyway must fail closed with ZERO
    checkpoint mutation instead of silently falling back to another
    variant."""
    from api import recovery_replan_loop as loop_module
    from api.routers.decisions import approve_proposal

    today = date(2026, 7, 13)
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    goal_plan = _transfer_ready_goal_plan(today, days_until=1)
    conflict_date = today + timedelta(days=1)
    goal_plan["protected_dates"] = [
        (conflict_date + timedelta(days=offset)).isoformat() for offset in (1, 2, 3)
    ]
    db = Database(str(tmp_path / "transfer-confirm-unknown-kind.db"))
    base = _save_plan(db, goal_plan)
    proposal = run_recovery_replan_loop(db, today=today)["proposal"]
    assert "transfer_1_3d" not in _variant_kinds(proposal)

    with pytest.raises(HTTPException) as error:
        approve_proposal(proposal["id"], db=db, variant_kind="transfer_1_3d")
    assert error.value.status_code == 422
    assert db.get_latest_planning_checkpoint()["id"] == base["id"]
    assert db.get_coach_proposal(proposal["id"])["status"] == "failed"


def test_approve_recovery_proposal_with_explicit_none_variant_kind_matches_legacy_downgrade(
    tmp_path,
    monkeypatch,
) -> None:
    """Legacy back-compat: an explicit `variant_kind=None` must behave
    exactly like today's omitted-argument downgrade contract (already
    pinned by test_recovery_proposal_reject_approve_and_append_only_rollback
    for the omitted-argument form), not like an unknown-kind rejection."""
    from api import recovery_replan_loop as loop_module
    from api.routers.decisions import approve_proposal

    today = date(2026, 7, 10)
    report = _conflict_report(today, days_until=4)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db = Database(str(tmp_path / "transfer-confirm-legacy-none.db"))
    base = _save_plan(db, _goal_plan(today, conflict_days_until=4))
    proposal = run_recovery_replan_loop(db, today=today)["proposal"]

    approved = approve_proposal(proposal["id"], db=db, variant_kind=None)

    assert approved["proposal"]["status"] == "approved"
    applied = db.get_latest_planning_checkpoint()
    assert applied["checkpoint_source"] == "recovery_replan"
    assert applied["checkpoint_parent_id"] == base["id"]


def test_approve_recovery_transfer_variant_applies_via_shared_primitive_and_rollback_is_append_only(
    tmp_path,
    monkeypatch,
) -> None:
    """Full M4 contract for the happy path: explicit `transfer_1_3d`
    selection routes through `apply_session_transfer` against the exact
    base checkpoint (never the near-term editor), appends exactly one
    `recovery_replan_transfer` checkpoint with auditable lineage, never
    calls the provider boundary, and rollback appends exactly one restored
    revision without deleting history."""
    from api import planning_service as planning_service_module
    from api import recovery_replan_loop as loop_module
    from api.routers import decisions as decisions_router
    from api.routers.decisions import approve_proposal, rollback_proposal

    today = date(2026, 7, 13)  # Monday
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)

    delivery_calls = []

    def fake_delivery(_db, *, dates, source, **_kwargs):
        delivery_calls.append({"dates": list(dates), "source": source})
        return {
            "status": "failed",
            "retryable": True,
            "error": "must not be called on the transfer path",
            "dates": list(dates),
        }

    monkeypatch.setattr(decisions_router, "safe_deliver_active_plan", fake_delivery, raising=False)

    near_term_calls = []
    original_apply_near_term = planning_service_module.apply_near_term_day_edits

    def spy_near_term(*args, **kwargs):
        near_term_calls.append(True)
        return original_apply_near_term(*args, **kwargs)

    monkeypatch.setattr(planning_service_module, "apply_near_term_day_edits", spy_near_term)

    db = Database(str(tmp_path / "transfer-confirm-happy-path.db"))
    base = _save_plan(db, _transfer_ready_goal_plan(today, days_until=1))
    proposal = run_recovery_replan_loop(db, today=today)["proposal"]
    transfer = _transfer_preview(proposal)
    source_date = transfer["source_date"]
    target_date = transfer["target_date"]
    old_session_id = transfer["replaced_session_id"]
    expected_new_session_id = transfer["new_session"]["session_id"]
    expected_new_tss = float(transfer["new_session"]["total_tss"])

    approved = approve_proposal(proposal["id"], db=db, variant_kind="transfer_1_3d")

    assert approved["proposal"]["status"] == "approved"
    result = approved["result"]
    assert result["selected_kind"] == "transfer_1_3d"
    assert result["old_session_id"] == old_session_id
    assert result["new_session_id"] == expected_new_session_id
    assert sorted(result["affected_dates"]) == sorted([source_date, target_date])
    assert result["rollback_checkpoint_id"] == base["id"]
    assert delivery_calls == []
    assert near_term_calls == []

    applied = db.get_latest_planning_checkpoint()
    assert applied["id"] == int(result["plan_id"])
    assert applied["checkpoint_source"] == "recovery_replan_transfer"
    assert applied["checkpoint_parent_id"] == base["id"]
    assert len(db.get_recent_planning_checkpoints(limit=10)) == 2  # base + applied only

    source_template = next(
        row
        for row in applied["goal_plan_snapshot"]["session_templates"]
        if row["date"] == source_date
    )
    assert old_session_id not in {
        s.get("session_id") for s in source_template.get("sessions", [])
    }
    target_template = next(
        row
        for row in applied["goal_plan_snapshot"]["session_templates"]
        if row["date"] == target_date
    )
    target_session = next(
        s
        for s in target_template.get("sessions", [])
        if s.get("session_id") == expected_new_session_id
    )
    assert float(target_session.get("total_tss")) == expected_new_tss
    assert target_session.get("replaces_session_id") == old_session_id

    rolled_back = rollback_proposal(proposal["id"], db=db)

    assert rolled_back["proposal"]["status"] == "rolled_back"
    assert delivery_calls == []  # still no provider call after rollback
    restored = db.get_latest_planning_checkpoint()
    assert restored["id"] > applied["id"]
    assert restored["checkpoint_source"] == "restore_version"
    assert restored["checkpoint_parent_id"] == applied["id"]
    assert restored["checkpoint_restored_from_checkpoint_id"] == base["id"]
    assert len(db.get_recent_planning_checkpoints(limit=10)) == 3  # base, applied, restored
    assert db.get_planning_checkpoint(base["id"]) is not None
    assert db.get_planning_checkpoint(applied["id"]) is not None
    restored_source_template = next(
        row
        for row in restored["goal_plan_snapshot"]["session_templates"]
        if row["date"] == source_date
    )
    assert old_session_id in {
        s.get("session_id") for s in restored_source_template.get("sessions", [])
    }


def test_approve_recovery_transfer_variant_refuses_stale_active_plan(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module
    from api.routers.decisions import approve_proposal

    today = date(2026, 7, 13)
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db = Database(str(tmp_path / "transfer-confirm-stale.db"))
    _save_plan(db, _transfer_ready_goal_plan(today, days_until=1))
    proposal = run_recovery_replan_loop(db, today=today)["proposal"]
    _save_plan(db, _transfer_ready_goal_plan(today, days_until=2))  # active checkpoint moves on

    with pytest.raises(HTTPException) as error:
        approve_proposal(proposal["id"], db=db, variant_kind="transfer_1_3d")
    assert error.value.status_code == 409
    assert db.get_coach_proposal(proposal["id"])["status"] == "failed"
    assert len(db.get_recent_planning_checkpoints(limit=10)) == 2  # no third checkpoint written


def test_approve_recovery_transfer_variant_serializes_concurrent_double_confirm(
    tmp_path,
    monkeypatch,
) -> None:
    from api import recovery_replan_loop as loop_module
    from api.routers.decisions import approve_proposal

    today = date(2026, 7, 13)
    report = _conflict_report(today, days_until=1)
    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)
    db = Database(str(tmp_path / "transfer-confirm-concurrent.db"))
    _save_plan(db, _transfer_ready_goal_plan(today, days_until=1))
    proposal = run_recovery_replan_loop(db, today=today)["proposal"]
    barrier = Barrier(2)

    def confirm(_sequence: int):
        barrier.wait()
        try:
            return approve_proposal(proposal["id"], db=db, variant_kind="transfer_1_3d")
        except HTTPException as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(confirm, (1, 2)))

    successes = [o for o in outcomes if not isinstance(o, HTTPException)]
    failures = [o for o in outcomes if isinstance(o, HTTPException)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 409
    assert len(db.get_recent_planning_checkpoints(limit=10)) == 2  # base + exactly one applied

"""RED/GREEN smoke coverage for Agent Log v2 (issue #501).

Agent Log v2 adds trigger / scope / outcome / revisit metadata to every
recorded coach decision, idempotent persistence by decision_event_id, and
legacy-row compatibility on the read path. These tests are written first
(RED): they fail against main at 79ff810..5308a96 and pass after the
implementation lands on branch codex/issue-501-agent-log-v2.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import time
from datetime import date, datetime, timedelta
from threading import Barrier

import pytest

from data.database import Database

pytestmark = pytest.mark.smoke


def _events(streaming_response) -> list[dict]:
    async def collect() -> list[dict]:
        out = []
        async for raw in streaming_response.body_iterator:
            text = raw if isinstance(raw, str) else raw.decode()
            if text.startswith("data:"):
                out.append(json.loads(text[5:].strip()))
        return out

    return asyncio.run(collect())


def _seeded_db(tmp_path, name: str = "coach.db") -> Database:
    db = Database(str(tmp_path / name))
    base = datetime.now()
    rows = []
    for i in range(35):
        rows.append(
            {
                "activity_id": f"coach-p{i}",
                "date": (base - timedelta(days=i)).strftime("%Y-%m-%d"),
                "sport": "cycling" if i % 2 else "running",
                "duration_minutes": 60,
                "distance_km": 20.0,
                "tss": 45.0 + (i % 5) * 4.0,
            }
        )
    db.save_activities(rows)
    return db


def _future_event_date(weeks: int = 8) -> str:
    return (datetime.now() + timedelta(weeks=weeks)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- model layer


def test_model_exposes_stable_agent_log_v2_contract():
    from models.coach_decisions import (
        DECISION_OUTCOMES,
        DECISION_SCOPES,
        DECISION_TRIGGERS,
        NO_REVISIT_REQUIRED,
        SCOPE_BY_PROPOSAL_ACTION,
        derive_decision_outcome,
    )

    assert DECISION_TRIGGERS >= {
        "coach_request",
        "scheduled_check",
        "provider_sync",
        "settings_change",
        "proposal_approved",
        "manual",
        "unknown",
    }
    assert DECISION_SCOPES >= {"today", "week", "plan", "unknown"}
    assert DECISION_OUTCOMES >= {
        "applied",
        "proposed",
        "no_change",
        "rejected",
        "failed",
        "rolled_back",
        "unknown",
    }
    assert NO_REVISIT_REQUIRED == "no_revisit_required"
    assert SCOPE_BY_PROPOSAL_ACTION["build_plan"] == "plan"
    assert SCOPE_BY_PROPOSAL_ACTION["recovery_replan"] == "week"
    assert SCOPE_BY_PROPOSAL_ACTION["repair_plan_day"] == "today"

    # No linkage -> unknown (legacy row must not be fabricated into a state).
    assert derive_decision_outcome({"decision_event_id": None}, []) == "unknown"
    assert derive_decision_outcome({"decision_event_id": "e1"}, []) == "unknown"
    # A stored snapshot is the honest fallback when nothing linked changed it.
    assert (
        derive_decision_outcome({"decision_event_id": "e1", "outcome": "no_change"}, [])
        == "no_change"
    )
    pending = [{"decision_event_id": "e1", "status": "pending"}]
    assert derive_decision_outcome({"decision_event_id": "e1"}, pending) == "proposed"
    approved = [{"decision_event_id": "e1", "status": "approved", "action": "build_plan",
                 "result": {"plan_id": 7}}]
    assert derive_decision_outcome({"decision_event_id": "e1"}, approved) == "applied"
    # Approved recovery `keep` is an audited no-op, mirroring drift semantics.
    keep = [{"decision_event_id": "e1", "status": "approved", "action": "recovery_replan",
             "result": {"selected_kind": "keep"}}]
    assert derive_decision_outcome({"decision_event_id": "e1"}, keep) == "no_change"
    rejected = [{"decision_event_id": "e1", "status": "rejected"}]
    assert derive_decision_outcome({"decision_event_id": "e1"}, rejected) == "rejected"
    failed = [{"decision_event_id": "e1", "status": "failed"}]
    assert derive_decision_outcome({"decision_event_id": "e1"}, failed) == "failed"
    rolled_back = [{"decision_event_id": "e1", "status": "rolled_back",
                    "action": "recovery_replan", "result": {"selected_kind": "downgrade_today"}}]
    assert derive_decision_outcome({"decision_event_id": "e1"}, rolled_back) == "rolled_back"


# ------------------------------------------------------------- persistence layer


def test_database_persists_agent_log_v2_fields(tmp_path):
    db = Database(str(tmp_path / "v2_fields.db"))
    saved = db.save_coach_decision(
        decision_type="Monitor",
        reason="Контрольная проверка без изменений.",
        decision_event_id="event-1",
        trigger="scheduled_check",
        trigger_source="acceptance:recovery-loop",
        scope="week",
        outcome="no_change",
        revisit_at="2026-10-01",
        revisit_reason="recheck after event_date change",
    )
    assert saved["trigger"] == "scheduled_check"
    assert saved["trigger_source"] == "acceptance:recovery-loop"
    assert saved["scope"] == "week"
    assert saved["outcome"] == "no_change"
    assert saved["revisit_at"] == "2026-10-01"
    assert saved["revisit_reason"] == "recheck after event_date change"

    rows = db.get_coach_decisions(days=36500)
    assert len(rows) == 1
    assert rows[0]["id"] == saved["id"]
    for key in ("trigger", "trigger_source", "scope", "outcome", "revisit_at", "revisit_reason"):
        assert rows[0][key] == saved[key]


def test_database_rejects_unknown_enum_values(tmp_path):
    db = Database(str(tmp_path / "enum_guard.db"))
    with pytest.raises(ValueError):
        db.save_coach_decision(
            decision_type="Monitor", reason="x", trigger="not-a-stable-trigger"
        )
    with pytest.raises(ValueError):
        db.save_coach_decision(decision_type="Monitor", reason="x", scope="decade")
    with pytest.raises(ValueError):
        db.save_coach_decision(decision_type="Monitor", reason="x", outcome="maybe")


def test_database_does_not_create_duplicate_logical_decision(tmp_path):
    db = Database(str(tmp_path / "idempotency.db"))
    first = db.save_coach_decision(
        decision_type="Monitor",
        reason="Первый прогон события.",
        decision_event_id="replayed-event-1",
        trigger="coach_request",
        scope="today",
        outcome="no_change",
    )
    # A replayed/retried event with the same logical id must not create a dup.
    second = db.save_coach_decision(
        decision_type="Push",
        reason="Повторный прогон того же события.",
        decision_event_id="replayed-event-1",
        trigger="coach_request",
        scope="plan",
        outcome="proposed",
    )
    assert second["id"] == first["id"]
    assert second["reason"] == first["reason"]
    rows = db.get_coach_decisions(days=36500)
    assert len(rows) == 1
    assert rows[0]["decision_event_id"] == "replayed-event-1"


def test_database_concurrent_replay_creates_one_logical_decision(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "concurrent_idempotency.db"))
    writers = 16
    start_together = Barrier(writers)
    original_clean_value = db.clean_value

    def aligned_clean_value(value):
        # Align every writer immediately before the event lookup. The fixed
        # implementation takes its write transaction after this normalization,
        # so the test amplifies the real race without reaching into SQL internals.
        if value == "concurrent-replay-1":
            start_together.wait(timeout=5)
        return original_clean_value(value)

    monkeypatch.setattr(db, "clean_value", aligned_clean_value)

    def save_replay(_index: int) -> int:
        row = db.save_coach_decision(
            decision_type="Monitor",
            reason="Один логический прогон.",
            decision_event_id="concurrent-replay-1",
            trigger="coach_request",
            trigger_source="coach:chat-1:message-1",
            scope="today",
            outcome="no_change",
            revisit_reason="no_revisit_required",
        )
        return int(row["id"])

    with ThreadPoolExecutor(max_workers=writers) as pool:
        returned_ids = list(pool.map(save_replay, range(writers)))

    assert len(set(returned_ids)) == 1
    rows = [
        row
        for row in db.get_coach_decisions(days=36500)
        if row["decision_event_id"] == "concurrent-replay-1"
    ]
    assert len(rows) == 1


def test_legacy_database_migrates_and_reads_metadata_as_null(tmp_path):
    # Reproduce the pre-#501 schema exactly, seed a legacy row, then let the
    # current Database open it and add the new columns additively.
    db_path = str(tmp_path / "legacy_v1.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE coach_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            workout_id TEXT,
            chat_id TEXT,
            message_id TEXT,
            metrics_window_days INTEGER,
            as_of_date TEXT,
            decision_event_id TEXT,
            narrative_gate_outcome TEXT,
            narrative_gate_reason_codes_json TEXT,
            narrative_gate_rule_version TEXT,
            narrative_evidence_version TEXT,
            narrative_evidence_fingerprint TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO coach_decisions (date, decision_type, reason, decision_event_id) "
        "VALUES (?, ?, ?, ?)",
        ("2026-08-20T09:00:00", "Monitor", "Legacy row without v2 metadata.", "legacy-evt"),
    )
    conn.commit()
    conn.close()

    db = Database(db_path)  # must migrate without crashing
    rows = db.get_coach_decisions(days=36500)
    assert len(rows) == 1
    assert rows[0]["decision_type"] == "Monitor"
    for key in ("trigger", "trigger_source", "scope", "outcome", "revisit_at", "revisit_reason"):
        assert rows[0][key] is None

    # New rows can be written to the migrated table and stay readable.
    saved = db.save_coach_decision(
        decision_type="Push",
        reason="Новая строка после миграции.",
        decision_event_id="post-migration",
        trigger="coach_request",
        scope="today",
        outcome="no_change",
    )
    assert saved["trigger"] == "coach_request"
    assert len(db.get_coach_decisions(days=36500)) == 2


# ------------------------------------------------------------------ API layer


def test_decisions_api_normalizes_legacy_rows_to_unknown(tmp_path):
    from api.routers.decisions import list_decisions

    db_path = str(tmp_path / "legacy_api.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE coach_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            workout_id TEXT,
            chat_id TEXT,
            message_id TEXT,
            metrics_window_days INTEGER,
            as_of_date TEXT,
            decision_event_id TEXT,
            narrative_gate_outcome TEXT,
            narrative_gate_reason_codes_json TEXT,
            narrative_gate_rule_version TEXT,
            narrative_evidence_version TEXT,
            narrative_evidence_fingerprint TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO coach_decisions (date, decision_type, reason) "
        "VALUES (?, ?, ?)",
        ("2026-08-20T09:00:00", "Recovery", "Legacy recovery advice."),
    )
    conn.commit()
    conn.close()
    db = Database(db_path)

    payload = list_decisions(days=36500, db=db)
    assert payload["has_data"] is True
    item = payload["days"][0]["decisions"][0]
    assert item["decision_type"] == "Recovery"
    assert item["trigger"] == "unknown"
    assert item["scope"] == "unknown"
    assert item["outcome"] == "unknown"
    assert item["revisit_at"] is None
    assert item["revisit_reason"] is None


def test_decisions_api_refreshes_outcome_from_proposal_lifecycle(tmp_path):
    from api.routers.decisions import list_decisions

    db = Database(str(tmp_path / "outcome_lifecycle.db"))
    today_iso = date.today().isoformat()
    decision = db.save_coach_decision(
        decision_type="Push",
        reason="Предлагаю собрать план.",
        decision_event_id="lifecycle-1",
        trigger="coach_request",
        scope="plan",
        outcome="proposed",
    )
    proposal = db.save_coach_proposal(
        action="build_plan",
        params={
            "goal_type": "Триатлон",
            "distance": "Olympic",
            "event_date": _future_event_date(),
            "available_hours": 10,
        },
        preview={"total_weeks": 8},
        date=f"{today_iso}T09:01:00",
        decision_event_id="lifecycle-1",
    )

    def item_for(payload: dict) -> dict:
        for day in payload["days"]:
            for item in day["decisions"]:
                if item["id"] == decision["id"]:
                    return item
        raise AssertionError("decision row missing from payload")

    payload = list_decisions(days=36500, db=db)
    assert item_for(payload)["outcome"] == "proposed"

    db.update_coach_proposal_status(proposal["id"], "approved", result={"plan_id": "1"})
    assert item_for(list_decisions(days=36500, db=db))["outcome"] == "applied"

    db.update_coach_proposal_status(proposal["id"], "rejected", result={"message": "no"})
    assert item_for(list_decisions(days=36500, db=db))["outcome"] == "rejected"


def test_decisions_api_shows_approved_keep_as_no_change(tmp_path):
    from api.routers.decisions import list_decisions

    db = Database(str(tmp_path / "keep.db"))
    today_iso = date.today().isoformat()
    db.save_coach_decision(
        decision_type="Recovery",
        reason="Готовность low: оставить план без изменений.",
        decision_event_id="keep-1",
        trigger="scheduled_check",
        scope="week",
        outcome="proposed",
    )
    proposal = db.save_coach_proposal(
        action="recovery_replan",
        params={"base_checkpoint_id": 1},
        preview={"variants": [{"kind": "keep"}]},
        date=f"{today_iso}T09:01:00",
        decision_event_id="keep-1",
    )
    db.update_coach_proposal_status(
        proposal["id"],
        "approved",
        result={"selected_kind": "keep", "affected_dates": []},
    )
    payload = list_decisions(days=36500, db=db)
    item = payload["days"][0]["decisions"][0]
    assert item["outcome"] == "no_change"


def test_decisions_api_does_not_group_distinct_v2_events(tmp_path):
    from api.routers.decisions import list_decisions

    db = Database(str(tmp_path / "distinct_v2_events.db"))
    common = {
        "decision_type": "Monitor",
        "reason": "Одинаковая видимая рекомендация.",
    }
    db.save_coach_decision(
        **common,
        date="2026-09-05T09:00:00",
        decision_event_id="event-coach",
        trigger="coach_request",
        trigger_source="coach:chat-1:message-1",
        scope="today",
        outcome="no_change",
        revisit_reason="no_revisit_required",
    )
    db.save_coach_decision(
        **common,
        date="2026-09-05T10:00:00",
        decision_event_id="event-sync",
        trigger="provider_sync",
        trigger_source="sync_job:intervals:run-1",
        scope="week",
        outcome="failed",
        revisit_reason="provider_available",
    )

    decisions = list_decisions(days=36500, db=db)["days"][0]["decisions"]
    assert len(decisions) == 2
    assert {item["trigger"] for item in decisions} == {
        "coach_request",
        "provider_sync",
    }
    assert all(item["count"] == 1 for item in decisions)


# ------------------------------------------------------------ coach write site


def test_coach_chat_turn_records_trigger_scope_outcome_revisit(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod
    from api.routers.decisions import list_decisions
    from models.mock_ai_provider import MockAIProvider

    provider = MockAIProvider(delay=0)
    monkeypatch.setattr(coach_mod, "resolve_provider", lambda provider_type=None: provider)
    monkeypatch.setattr(coach_mod, "supports_streaming", lambda _provider: False)

    db = Database(str(tmp_path / "coach_v2.db"))
    req = coach_mod.ChatRequest(
        message="Что делать сегодня при усталости?",
        provider="mock",
    )
    events = _events(coach_mod.coach_chat(req, db))
    assert events[-1]["type"] == "done"

    rows = db.get_coach_decisions(days=30)
    assert len(rows) == 1
    decision = rows[0]
    assert decision["decision_event_id"]
    assert decision["trigger"] == "coach_request"
    assert decision["scope"] == "today"
    assert decision["outcome"] == "no_change"
    assert decision["trigger_source"].startswith("coach:")
    # Every new product decision states revisit explicitly: none required now.
    assert decision["revisit_reason"] == "no_revisit_required"
    assert decision["revisit_at"] is None

    payload = list_decisions(days=30, db=db)
    item = payload["days"][0]["decisions"][0]
    assert item["trigger"] == "coach_request"
    assert item["scope"] == "today"
    assert item["outcome"] == "no_change"


def test_coach_proposal_turn_records_plan_scope_and_applies_outcome(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod
    from api.routers.decisions import approve_proposal, list_decisions
    from models.mock_ai_provider import MockAIProvider

    class ProposalProvider(MockAIProvider):
        def __init__(self):
            super().__init__(delay=0)
            self.calls = 0

        def generate_response(self, prompt: str, context: str = "") -> str:
            self.calls += 1
            if self.calls == 1:
                return (
                    "[TOOL: propose_plan_build, goal_type=Триатлон, "
                    f"distance=Olympic, event_date={_future_event_date()}, available_hours=10]"
                )
            return "Готово: я подготовил предложение плана, его нужно подтвердить."

    provider = ProposalProvider()
    monkeypatch.setattr(coach_mod, "resolve_provider", lambda provider_type=None: provider)
    monkeypatch.setattr(coach_mod, "supports_streaming", lambda _provider: False)

    db = _seeded_db(tmp_path, "coach_proposal_v2.db")
    req = coach_mod.ChatRequest(
        message="Собери план на олимпийку.",
        provider="mock",
    )
    events = _events(coach_mod.coach_chat(req, db))
    proposals = [event for event in events if event["type"] == "proposal"]
    assert len(proposals) == 1

    decision = db.get_coach_decisions(days=30)[0]
    proposal = db.get_coach_proposal(proposals[0]["proposal_id"])
    assert proposal["decision_event_id"] == decision["decision_event_id"]
    assert decision["trigger"] == "coach_request"
    assert decision["scope"] == "plan"
    assert decision["outcome"] == "proposed"
    assert decision["revisit_reason"] == "proposal_resolved"

    payload = list_decisions(days=30, db=db)
    item = next(
        row for day in payload["days"] for row in day["decisions"]
        if row["id"] == decision["id"]
    )
    assert item["scope"] == "plan"
    assert item["outcome"] == "proposed"

    approve_proposal(proposal["id"], db=db)
    payload = list_decisions(days=30, db=db)
    item = next(
        row for day in payload["days"] for row in day["decisions"]
        if row["id"] == decision["id"]
    )
    assert item["outcome"] == "applied"

    approval = next(
        row
        for row in db.get_coach_decisions(days=30)
        if row["trigger"] == "proposal_approved"
    )
    assert approval["trigger_source"] == f"proposal:{proposal['id']}"
    assert approval["scope"] == "plan"
    assert approval["outcome"] == "applied"
    assert approval["revisit_reason"] == "no_revisit_required"


def test_scheduled_recovery_check_records_source_and_revisit(tmp_path):
    from api.recovery_replan_loop import run_recovery_replan_loop

    db = Database(str(tmp_path / "scheduled_check.db"))
    result = run_recovery_replan_loop(db, today=date(2026, 9, 5))
    assert result["outcome"] == "data_gap"

    decisions = db.get_coach_decisions(days=36500)
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["trigger"] == "scheduled_check"
    assert decision["trigger_source"].startswith("recovery_check:")
    assert decision["scope"] == "week"
    assert decision["outcome"] == "failed"
    assert decision["revisit_reason"] == "next_scheduled_check"


def test_sync_job_records_provider_trigger_for_success_and_failure(tmp_path):
    from api.sync_jobs import SyncJobManager

    db = Database(str(tmp_path / "sync_events.db"))

    def wait_done(manager: SyncJobManager) -> dict:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            snapshot = manager.status(db=db)
            if snapshot["sync_state"] != "running":
                return snapshot
            time.sleep(0.01)
        raise AssertionError("sync job did not finish")

    succeeded = SyncJobManager()
    succeeded.start_or_get(
        days=7,
        source="intervals",
        db=db,
        run_sync=lambda _progress: {"sync_state": "succeeded", "title": "ok"},
    )
    assert wait_done(succeeded)["sync_state"] == "succeeded"

    failed = SyncJobManager()

    def fail_sync(_progress):
        raise RuntimeError("provider unavailable")

    failed.start_or_get(
        days=30,
        source="garmin",
        db=db,
        run_sync=fail_sync,
    )
    assert wait_done(failed)["sync_state"] == "failed"

    decisions = {
        row["trigger_source"]: row for row in db.get_coach_decisions(days=36500)
    }
    interval_event = next(
        row for source, row in decisions.items() if source.startswith("sync_job:intervals:")
    )
    garmin_event = next(
        row for source, row in decisions.items() if source.startswith("sync_job:garmin:")
    )
    assert interval_event["trigger"] == "provider_sync"
    assert interval_event["scope"] == "week"
    assert interval_event["outcome"] == "applied"
    assert interval_event["revisit_reason"] == "no_revisit_required"
    assert garmin_event["scope"] == "plan"
    assert garmin_event["outcome"] == "failed"
    assert garmin_event["revisit_reason"] == "provider_available"


def test_briefing_setting_change_records_applied_and_no_change(tmp_path):
    from api.routers.settings import BriefingFrequencyRequest, put_briefing_settings

    db = Database(str(tmp_path / "settings_events.db"))
    put_briefing_settings(
        BriefingFrequencyRequest(frequency="conflicts_only"),
        db=db,
    )
    put_briefing_settings(
        BriefingFrequencyRequest(frequency="conflicts_only"),
        db=db,
    )

    rows = [
        row
        for row in db.get_coach_decisions(days=36500)
        if row["trigger"] == "settings_change"
    ]
    assert len(rows) == 2
    assert {row["outcome"] for row in rows} == {"applied", "no_change"}
    assert all(row["trigger_source"].startswith("settings:briefing:") for row in rows)
    assert all(row["scope"] == "plan" for row in rows)
    assert all(row["revisit_reason"] == "no_revisit_required" for row in rows)

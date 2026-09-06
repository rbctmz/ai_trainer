"""Smoke coverage for the coach decision audit trail."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta

import pytest

from data.database import Database


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


def test_database_persists_coach_decisions(tmp_path):
    db = Database(str(tmp_path / "decisions.db"))

    saved = db.save_coach_decision(
        decision_type="Recovery",
        reason="TSB -24.0: лучше снизить интенсивность сегодня.",
        chat_id="chat-1",
        message_id="msg-1",
    )

    assert saved["id"]
    assert saved["decision_type"] == "Recovery"
    assert saved["reason"] == "TSB -24.0: лучше снизить интенсивность сегодня."
    assert saved["chat_id"] == "chat-1"
    assert saved["message_id"] == "msg-1"
    assert saved["created_at"]

    rows = db.get_coach_decisions(days=30)
    assert len(rows) == 1
    assert rows[0]["id"] == saved["id"]
    assert rows[0]["date"] == saved["date"]


def test_database_persists_coach_proposals(tmp_path):
    db = Database(str(tmp_path / "proposals.db"))

    proposal = db.save_coach_proposal(
        action="build_plan",
        params={
            "goal_type": "Триатлон",
            "distance": "Olympic",
            "event_date": "2026-09-01",
            "available_hours": 10,
            "available_days": ["mon", "wed", "sat"],
        },
        preview={"total_weeks": 8, "peak_tss": 240},
        chat_id="chat-1",
        message_id="msg-1",
    )

    assert proposal["id"]
    assert proposal["status"] == "pending"
    assert proposal["action"] == "build_plan"
    assert proposal["params"]["distance"] == "Olympic"
    assert proposal["preview"]["peak_tss"] == 240
    assert proposal["chat_id"] == "chat-1"
    assert proposal["message_id"] == "msg-1"

    fetched = db.get_coach_proposal(proposal["id"])
    assert fetched == proposal

    rows = db.get_coach_proposals(days=30)
    assert [row["id"] for row in rows] == [proposal["id"]]


def test_decisions_api_groups_by_day_and_exposes_empty_state(tmp_path, monkeypatch):
    from api.routers.decisions import list_decisions
    from config.settings import Settings

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "UTC")

    db = Database(str(tmp_path / "decisions.db"))

    empty = list_decisions(db=db)
    assert empty["has_data"] is False
    assert empty["days"] == []
    assert empty["operational_state"]["status"] == "empty"

    # Date-safe fixtures (issue #320): stay inside the rolling 30-day window
    # used by get_coach_decisions(days=30) instead of hardcoded dates that
    # silently expire as the calendar advances.
    today = date.today()
    recent_day = today - timedelta(days=1)
    older_day = today - timedelta(days=2)
    db.save_coach_decision("Monitor", "Недостаточно сильного сигнала для изменения нагрузки.", date=f"{recent_day.isoformat()}T09:00:00")
    db.save_coach_decision("Push", "TSB +5.0 и readiness 82: можно выполнить качественную работу.", date=f"{recent_day.isoformat()}T12:00:00")
    db.save_coach_decision("Recovery", "TSB -25.0: восстановительный день приоритетнее.", date=f"{older_day.isoformat()}T08:00:00")

    payload = list_decisions(db=db)
    assert payload["has_data"] is True
    assert [day["date"] for day in payload["days"]] == [recent_day.isoformat(), older_day.isoformat()]
    assert [item["decision_type"] for item in payload["days"][0]["decisions"]] == ["Push", "Monitor"]
    assert payload["days"][0]["decisions"][0]["time"] == "12:00"
    assert payload["operational_state"]["status"] == "ready"


def test_decisions_api_collapses_consecutive_identical_decisions(tmp_path, monkeypatch):
    from api.routers.decisions import list_decisions
    from config.settings import Settings

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "UTC")

    db = Database(str(tmp_path / "decision_dedup.db"))
    # Date-safe fixtures (issue #320): keep dates inside the rolling 30-day
    # window used by list_decisions, instead of hardcoded dates that age out.
    today = date.today()
    recent_day = today - timedelta(days=1)
    older_day = today - timedelta(days=2)
    repeated_reason = "TSB -18.1: держите нагрузку контролируемой."
    for hour in range(9, 12):
        db.save_coach_decision(
            "Moderate", repeated_reason, date=f"{recent_day.isoformat()}T{hour:02d}:00:00"
        )
    db.save_coach_decision(
        "Push", "TSB +5.0: можно качественную работу.", date=f"{recent_day.isoformat()}T13:00:00"
    )
    db.save_coach_decision(
        "Moderate", repeated_reason, date=f"{recent_day.isoformat()}T14:00:00"
    )
    db.save_coach_decision(
        "Moderate", repeated_reason, date=f"{older_day.isoformat()}T10:00:00"
    )

    payload = list_decisions(db=db)

    assert payload["count"] == 6
    assert [day["date"] for day in payload["days"]] == [recent_day.isoformat(), older_day.isoformat()]

    day_items = payload["days"][0]["decisions"]
    assert [(item["decision_type"], item["count"]) for item in day_items] == [
        ("Moderate", 1),
        ("Push", 1),
        ("Moderate", 3),
    ]
    collapsed = day_items[2]
    assert collapsed["reason"] == repeated_reason
    assert collapsed["time"] == "11:00"
    assert collapsed["first_time"] == "09:00"

    other_day = payload["days"][1]["decisions"]
    assert [(item["count"], item["time"]) for item in other_day] == [(1, "10:00")]


def test_decisions_api_exposes_proposals_without_changing_decision_days(tmp_path):
    from api.routers.decisions import list_decisions

    # Date-safe fixtures (issue #320): stay inside the rolling 30-day window
    # used by get_coach_decisions/get_coach_proposals(days=30) instead of
    # hardcoded dates that silently expire as the calendar advances.
    today = date.today()
    today_iso = today.isoformat()
    db = Database(str(tmp_path / "decision_proposals.db"))
    db.save_coach_decision("Monitor", "Недостаточно сильного сигнала.", date=f"{today_iso}T09:00:00")
    pending = db.save_coach_proposal(
        action="build_plan",
        params={
            "goal_type": "Триатлон",
            "distance": "Olympic",
            "event_date": "2026-09-01",
            "available_hours": 10,
        },
        preview={"total_weeks": 8},
        date=f"{today_iso}T09:01:00",
    )
    approved = db.save_coach_proposal(
        action="adjust_plan",
        params={"rows": [], "weeks": 1},
        preview={"adjustment_status": "preview"},
        date=f"{today_iso}T09:02:00",
    )
    db.update_coach_proposal_status(approved["id"], "approved", result={"plan_id": "1"})

    payload = list_decisions(db=db)

    assert payload["count"] == 1
    assert len(payload["days"]) == 1
    assert payload["proposal_count"] == 2
    assert payload["proposal_days"][0]["date"] == today_iso
    assert [item["id"] for item in payload["proposal_days"][0]["proposals"]] == [
        approved["id"],
        pending["id"],
    ]
    assert payload["pending_proposal_count"] == 1
    assert payload["pending_proposal_days"][0]["date"] == today_iso
    assert payload["pending_proposal_days"][0]["proposals"][0]["id"] == pending["id"]
    assert payload["pending_proposal_days"][0]["proposals"][0]["status"] == "pending"


def test_display_time_converts_utc_to_athlete_timezone_and_falls_back(monkeypatch):
    from api.routers.decisions import _display_day, _display_time
    from config.settings import Settings

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow")

    # Coach rows carry a UTC clock in `date` -> render it for the athlete.
    assert (
        _display_time({"date": "2026-07-02T12:00:00", "created_at": "2026-07-02 09:00:00"})
        == "15:00"
    )
    # Recovery/loop rows persist `<as_of>T00:00:00` -> use the creation clock.
    assert (
        _display_time(
            {
                "date": "2026-07-20T00:00:00",
                "created_at": "2026-07-20 08:19:56",
                "source": "recovery_replan",
            }
        )
        == "11:19"
    )
    # A bare date with no time component also falls back to created_at.
    assert (
        _display_time({"date": "2026-07-20", "created_at": "2026-07-20 08:19:56"}) == "11:19"
    )
    # Nothing to show anywhere stays empty (renders as "--:--" in the UI).
    assert _display_time({"date": "", "created_at": ""}) == ""
    # 00:00 business date with no created_at keeps the honest 00:00.
    assert _display_time(
        {"date": "2026-07-20T00:00:00", "source": "recovery_replan"}
    ) == "00:00"

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "invalid/timezone")
    assert _display_time({"date": "2026-07-20T08:19:56"}) == "08:19 UTC"

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow")
    after_midnight = {"date": "2026-07-02T22:30:00Z"}
    assert _display_time(after_midnight) == "01:30"
    assert _display_day(after_midnight) == "2026-07-03"
    assert _display_day(
        {
            "date": "2026-07-02T00:00:00",
            "created_at": "2026-07-03",
            "source": "recovery_replan",
        }
    ) == "2026-07-02"


def test_decisions_api_shows_local_recovery_creation_time_not_business_midnight(
    tmp_path, monkeypatch
):
    from api.routers.decisions import _format_time, _display_time, list_decisions
    from config.settings import Settings

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow")

    db = Database(str(tmp_path / "recovery_time.db"))
    saved = db.save_recovery_decision(
        fingerprint="recovery-time-fp",
        outcome="silence",
        reason="План и состояние согласны.",
        report={"conflicts": [], "silence": True, "data_gap": False},
        plan_checkpoint_id=1,
        date="2026-07-20T00:00:00",  # business date the loop always writes
    )
    created_at = saved["decision"]["created_at"]

    payload = list_decisions(days=36500, db=db)
    recovery = payload["recovery_days"][0]["recovery_decisions"][0]

    # The stored business date carries no clock (00:00); the displayed time must
    # come from created_at instead of the hard-coded midnight.
    assert _format_time("2026-07-20T00:00:00") == "00:00"
    assert recovery["time"] == _display_time({"created_at": created_at})


def test_decisions_api_groups_real_utc_clocks_by_athlete_local_day(
    tmp_path, monkeypatch
) -> None:
    from api.routers.decisions import list_decisions
    from config.settings import Settings

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow")
    db = Database(str(tmp_path / "local-day-grouping.db"))
    db.save_coach_decision(
        decision_type="Monitor",
        reason="Late UTC decision.",
        decision_event_id="late-decision",
        outcome="no_change",
        date="2026-07-02T22:30:00Z",
    )
    db.save_coach_proposal(
        action="build_plan",
        params={},
        preview={},
        source_key="late-proposal",
        date="2026-07-02T22:45:00Z",
    )
    db.save_recovery_decision(
        fingerprint="business-date-midnight",
        outcome="silence",
        reason="Business date stays authoritative.",
        report={},
        date="2026-07-02T00:00:00",
    )

    payload = list_decisions(days=36500, db=db)

    assert payload["days"][0]["date"] == "2026-07-03"
    assert payload["days"][0]["decisions"][0]["time"] == "01:30"
    assert payload["proposal_days"][0]["date"] == "2026-07-03"
    assert payload["proposal_days"][0]["proposals"][0]["time"] == "01:45"
    assert payload["recovery_days"][0]["date"] == "2026-07-02"


def test_decisions_api_localizes_real_midnight_by_row_semantics(
    tmp_path, monkeypatch
) -> None:
    from api.routers.decisions import list_decisions
    from config.settings import Settings

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "America/Los_Angeles")
    db = Database(str(tmp_path / "real-midnight-grouping.db"))
    db.save_coach_proposal(
        action="build_plan",
        params={},
        preview={},
        source_key="real-midnight-proposal",
        date="2026-07-03T00:00:00Z",
    )
    db.save_coach_decision(
        decision_type="Monitor",
        reason="Real midnight decision.",
        decision_event_id="real-midnight-decision",
        outcome="no_change",
        date="2026-07-03T00:00:00Z",
    )
    db.save_recovery_decision(
        fingerprint="recovery-business-midnight",
        outcome="silence",
        reason="Recovery business date remains authoritative.",
        report={},
        date="2026-07-03T00:00:00Z",
    )

    payload = list_decisions(days=36500, db=db)

    assert payload["proposal_days"][0]["date"] == "2026-07-02"
    assert payload["proposal_days"][0]["proposals"][0]["time"] == "17:00"
    assert payload["days"][0]["date"] == "2026-07-02"
    assert payload["days"][0]["decisions"][0]["time"] == "17:00"
    assert payload["recovery_days"][0]["date"] == "2026-07-03"


def test_decisions_api_dedupes_recovery_conflict_rules(tmp_path):
    from api.routers.decisions import list_decisions

    db = Database(str(tmp_path / "recovery_conflicts.db"))
    report = {
        "as_of": "2026-07-20",
        "readiness": {"score": 38, "status": "low", "confidence": 0.8},
        "conflicts": [
            {"date": "2026-07-20", "severity": "medium", "kind": "low_readiness_easy_session"},
            {"date": "2026-07-21", "severity": "medium", "kind": "low_readiness_easy_session"},
            {"date": "2026-07-22", "severity": "medium", "kind": "low_readiness_easy_session"},
            {"date": "2026-07-23", "severity": "high", "kind": "low_readiness_quality_session"},
        ],
        "silence": False,
        "data_gap": False,
        "reason": "Готовность low расходится с планом.",
    }
    db.save_recovery_decision(
        fingerprint="recovery-conflicts-fp",
        outcome="conflict",
        reason=report["reason"],
        report=report,
        plan_checkpoint_id=1,
        date="2026-07-20T00:00:00",
    )

    payload = list_decisions(days=36500, db=db)
    recovery = payload["recovery_days"][0]["recovery_decisions"][0]

    # One row per unique severity·rule, first-seen order preserved.
    assert recovery["conflict_rules"] == [
        {"severity": "medium", "kind": "low_readiness_easy_session"},
        {"severity": "high", "kind": "low_readiness_quality_session"},
    ]
    # The audited report keeps every distinct-date conflict untouched.
    assert len(recovery["report"]["conflicts"]) == 4


def test_approve_build_plan_proposal_persists_checkpoint(tmp_path):
    from api.routers.decisions import approve_proposal
    from api.planning_service import get_active_plan

    db = _seeded_db(tmp_path, "approve_build.db")
    event_date = _future_event_date()
    proposal = db.save_coach_proposal(
        action="build_plan",
        params={
            "goal_type": "Триатлон",
            "distance": "Olympic",
            "event_date": event_date,
            "available_hours": 10,
            "available_days": ["mon", "wed", "sat", "sun"],
        },
        preview={"total_weeks": 8},
    )

    payload = approve_proposal(proposal["id"], db=db)

    assert payload["proposal"]["status"] == "approved"
    assert payload["proposal"]["resolved_at"]
    assert payload["result"]["plan_id"]
    latest = db.get_latest_planning_checkpoint()
    assert latest is not None
    assert str(latest["id"]) == str(payload["result"]["plan_id"])
    assert latest["event_date"] == event_date
    assert latest["goal_plan_snapshot"]["event_date"] == event_date
    active_plan = get_active_plan(db)
    assert active_plan is not None
    assert active_plan["event_date"] == event_date


def test_coach_build_proposal_records_and_guards_its_preview_base(tmp_path):
    from fastapi import HTTPException

    from api import planning_service
    from api.routers.decisions import approve_proposal
    from models.ai_tools import AITools

    db = _seeded_db(tmp_path, "stale_build.db")
    initial = planning_service.build_plan(
        db,
        goal_type="Триатлон",
        distance="Olympic",
        event_date=_future_event_date(weeks=10),
        available_hours=10,
        available_days=["mon", "wed", "sat", "sun"],
        persist=True,
    )
    raw = AITools(db).propose_plan_build(
        goal_type="Триатлон",
        distance="Olympic",
        event_date=_future_event_date(weeks=12),
        available_hours=10,
        available_days="mon,wed,sat,sun",
    )
    assert raw["params"]["base_checkpoint_id"] == int(initial["plan_id"])
    proposal = db.save_coach_proposal(
        action=raw["action"],
        params=raw["params"],
        preview=raw["preview"],
        decision_event_id="event-stale-build",
    )
    assert proposal["base_checkpoint_id"] == int(initial["plan_id"])

    # Another append-only plan version wins before approval. The old preview
    # must fail closed instead of producing misleading drift lineage.
    planning_service.build_plan(
        db,
        goal_type="Триатлон",
        distance="Olympic",
        event_date=_future_event_date(weeks=11),
        available_hours=10,
        available_days=["mon", "wed", "sat", "sun"],
        persist=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        approve_proposal(proposal["id"], db=db)

    assert exc_info.value.status_code == 409
    assert db.get_coach_proposal(proposal["id"])["status"] == "failed"


def test_reject_plan_proposal_does_not_mutate_active_plan(tmp_path):
    from api.routers.decisions import reject_proposal

    db = _seeded_db(tmp_path, "reject_build.db")
    proposal = db.save_coach_proposal(
        action="build_plan",
        params={
            "goal_type": "Триатлон",
            "distance": "Olympic",
            "event_date": _future_event_date(),
            "available_hours": 10,
        },
        preview={"total_weeks": 8},
    )

    payload = reject_proposal(proposal["id"], db=db)

    assert payload["proposal"]["status"] == "rejected"
    assert db.get_latest_planning_checkpoint() is None


def test_approve_adjust_plan_proposal_persists_adjusted_checkpoint(tmp_path):
    from api import planning_service
    from api.routers.decisions import approve_proposal

    db = _seeded_db(tmp_path, "approve_adjust.db")
    initial = planning_service.build_plan(
        db,
        goal_type="Триатлон",
        distance="Olympic",
        event_date=_future_event_date(),
        available_hours=10,
        available_days=["mon", "wed", "sat", "sun"],
        persist=True,
    )
    rows = planning_service.reconciliation(db, weeks=1)["rows"]
    proposal = db.save_coach_proposal(
        action="adjust_plan",
        params={"rows": rows, "weeks": 1},
        preview={"adjustment_status": "preview"},
    )

    payload = approve_proposal(proposal["id"], db=db)

    assert payload["proposal"]["status"] == "approved"
    assert payload["result"]["plan_id"]
    assert payload["result"]["plan_id"] != initial["plan_id"]
    latest = db.get_latest_planning_checkpoint()
    assert str(latest["id"]) == str(payload["result"]["plan_id"])


def test_coach_completion_writes_decision_record(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod
    from api.routers.decisions import list_decisions

    db = Database(str(tmp_path / "coach.db"))
    req = coach_mod.ChatRequest(
        message="Что делать сегодня при усталости?",
        provider="mock",
    )

    resp = coach_mod.coach_chat(req, db)
    events = _events(resp)

    assert events[-1]["type"] == "done"
    payload = list_decisions(db=db)
    assert payload["has_data"] is True
    assert len(payload["days"]) == 1
    decision = payload["days"][0]["decisions"][0]
    assert decision["decision_type"] in {"Push", "Moderate", "Recovery", "Monitor"}
    assert decision["reason"]
    assert "\n" not in decision["reason"]
    assert decision["chat_id"] == events[0]["chat_id"]
    assert decision["message_id"] == events[-1]["message_id"]
    assert decision["decision_event_id"]


def test_coach_stream_persists_proposal_and_emits_id(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod
    from models.mock_ai_provider import MockAIProvider

    event_date = _future_event_date()

    class ProposalProvider(MockAIProvider):
        def __init__(self):
            super().__init__(delay=0)
            self.calls = 0

        def generate_response(self, prompt: str, context: str = "") -> str:
            self.calls += 1
            if self.calls == 1:
                return (
                    "[TOOL: propose_plan_build, goal_type=Триатлон, "
                    f"distance=Olympic, event_date={event_date}, available_hours=10]"
                )
            return "Готово: я подготовил предложение плана, его нужно подтвердить."

    provider = ProposalProvider()
    monkeypatch.setattr(coach_mod, "resolve_provider", lambda provider_type=None: provider)
    monkeypatch.setattr(coach_mod, "supports_streaming", lambda _provider: False)

    db = _seeded_db(tmp_path, "coach_proposal_stream.db")
    req = coach_mod.ChatRequest(
        message="Собери план на олимпийку.",
        provider="mock",
    )

    events = _events(coach_mod.coach_chat(req, db))
    proposals = [event for event in events if event["type"] == "proposal"]

    assert len(proposals) == 1
    assert proposals[0]["proposal_id"]
    assert proposals[0]["status"] == "pending"

    saved = db.get_coach_proposal(proposals[0]["proposal_id"])
    assert saved["action"] == "build_plan"
    assert saved["status"] == "pending"
    assert saved["source"] == "coach_tool"
    assert saved["chat_id"] == events[0]["chat_id"]
    assert saved["message_id"] == events[-1]["message_id"]
    decision = db.get_coach_decisions(days=30)[0]
    assert saved["decision_event_id"]
    assert saved["decision_event_id"] == decision["decision_event_id"]


def test_routes_register_decisions_endpoint():
    import importlib

    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert "/api/decisions" in paths
    assert "/api/decisions/proposals/{proposal_id}/approve" in paths
    assert "/api/decisions/proposals/{proposal_id}/reject" in paths
    assert "/api/decisions/proposals/{proposal_id}/rollback" in paths

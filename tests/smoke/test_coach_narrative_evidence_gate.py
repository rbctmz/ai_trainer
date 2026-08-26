"""Deterministic RED/GREEN coverage for issue #499."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import date, datetime, timezone

import pytest

from models.coach_narrative_evidence import (
    build_coach_narrative_evidence,
    validate_coach_narrative,
)


pytestmark = pytest.mark.smoke

OBSERVED_AT = datetime(2026, 8, 23, 21, 30, tzinfo=timezone.utc)


def _snapshot(*, status: str = "strong", hrv_score: float = 85.0) -> dict:
    return {
        "score": 82.0,
        "status": status,
        "confidence": 1.0,
        "stale": False,
        "is_provisional": False,
        "missing_inputs": [],
        "rule_version": "readiness_today_v1",
        "factors": [
            {
                "key": "hrv",
                "score": hrv_score,
                "raw_value": 56.0,
                "baseline": 53.0,
                "deviation": 5.7,
                "as_of": "2026-08-24",
                "source": "rmssd",
                "stale_input": False,
            }
        ],
    }


def _evidence(**overrides):
    values = {
        "readiness_snapshot": _snapshot(),
        "tool_results": [],
        "session_evidence": None,
        "goal_plan": {"event_date": "2026-08-30"},
        "athlete_timezone": "Europe/Moscow",
        "observed_at_utc": OBSERVED_AT,
    }
    values.update(overrides)
    return build_coach_narrative_evidence(**values)


def test_green_readiness_blocks_poor_recovery_and_suppressed_hrv_claims():
    raw = "Восстановление плохое, HRV подавлен — сегодня нужен полный отдых."

    result = validate_coach_narrative(raw, _evidence())

    assert result.outcome == "replaced"
    assert result.reason_codes == (
        "READINESS_CLAIM_CONTRADICTED",
        "HRV_CLAIM_CONTRADICTED",
    )
    assert raw not in result.delivered_text
    assert "readiness 82" in result.delivered_text


def test_missing_readiness_is_an_explicit_data_gap():
    result = validate_coach_narrative(
        "Восстановление плохое — нагрузку нужно снизить.",
        _evidence(readiness_snapshot={"score": None, "status": "unknown"}),
    )

    assert result.outcome == "data_gap"
    assert result.reason_codes == ("READINESS_EVIDENCE_MISSING",)
    assert "данных недостаточно" in result.delivered_text.lower()


def test_trend_claim_without_comparator_is_refused():
    result = validate_coach_narrative(
        "HRV улучшается, а эта тренировка лучше прошлой.",
        _evidence(),
    )

    assert result.outcome == "data_gap"
    assert result.reason_codes == ("TREND_COMPARATOR_MISSING",)


def test_supported_hrv_trend_and_neutral_advice_pass_byte_identical():
    raw = "HRV улучшается относительно 28-дневной базовой линии. Держи план ровно.\n"
    tools = [
        {
            "tool_name": "analyze_hrv_trends",
            "success": True,
            "raw_result": {
                "data_points": 14,
                "current_rmssd": 56.0,
                "baseline_median": 53.0,
                "trend_direction": "improving",
            },
        }
    ]

    result = validate_coach_narrative(raw, _evidence(tool_results=tools))

    assert result.outcome == "pass"
    assert result.delivered_text == raw
    assert result.reason_codes == ()


def test_comparable_session_guardrail_blocks_causal_adaptation_claim() -> None:
    tools = [
        {
            "tool_name": "get_comparable_session",
            "success": True,
            "raw_result": {
                "status": "available",
                "target": {"activity_id": "target", "tss": 70},
                "comparator": {"activity_id": "prior", "tss": 60},
                "guardrails": {
                    "one_comparison_only": True,
                    "trend_claim_allowed": False,
                    "causal_claim_allowed": False,
                },
            },
        }
    ]

    result = validate_coach_narrative(
        "Более высокий TSS вызван адаптацией.",
        _evidence(tool_results=tools),
    )

    assert result.outcome == "data_gap"
    assert result.reason_codes == ("CAUSAL_CLAIM_UNSUPPORTED",)
    assert "не доказывает причину" in result.delivered_text.lower()


def test_comparable_session_guardrail_allows_explicit_non_causal_disclaimer() -> None:
    tools = [
        {
            "tool_name": "get_comparable_session",
            "success": True,
            "raw_result": {
                "status": "available",
                "guardrails": {"causal_claim_allowed": False},
            },
        }
    ]
    raw = "Одно сравнение не доказывает тренд, адаптацию или причину."

    result = validate_coach_narrative(raw, _evidence(tool_results=tools))

    assert result.outcome == "pass"
    assert result.delivered_text == raw


def test_comparable_session_guardrail_does_not_block_adaptation_plan_advice() -> None:
    tools = [
        {
            "tool_name": "get_comparable_session",
            "success": True,
            "raw_result": {
                "status": "available",
                "guardrails": {"causal_claim_allowed": False},
            },
        }
    ]
    raw = "Сохраняй план адаптации к жаре и контролируй питьё."

    result = validate_coach_narrative(raw, _evidence(tool_results=tools))

    assert result.outcome == "pass"
    assert result.delivered_text == raw


def test_trend_direction_must_match_structured_comparator():
    tools = [
        {
            "tool_name": "analyze_hrv_trends",
            "success": True,
            "raw_result": {
                "data_points": 14,
                "current_rmssd": 56.0,
                "baseline_median": 53.0,
                "trend_direction": "improving",
            },
        }
    ]

    result = validate_coach_narrative(
        "HRV снижается относительно базовой линии.",
        _evidence(tool_results=tools),
    )

    assert result.outcome == "replaced"
    assert result.reason_codes == ("TREND_CLAIM_CONTRADICTED",)


def test_calendar_uses_athlete_timezone_at_utc_midnight_boundary():
    correct = (
        "Сегодня понедельник, 2026-08-24. Вчера было 2026-08-23. "
        "До старта 6 дней."
    )
    wrong = (
        "Сегодня воскресенье, 2026-08-23. Вчера было 2026-08-22. "
        "До старта 7 дней."
    )

    passed = validate_coach_narrative(correct, _evidence())
    blocked = validate_coach_narrative(wrong, _evidence())

    assert passed.outcome == "pass"
    assert passed.delivered_text == correct
    assert blocked.outcome == "replaced"
    assert blocked.reason_codes == ("CALENDAR_REFERENCE_MISMATCH",)
    assert "2026-08-24" in blocked.delivered_text
    assert "Europe/Moscow" in blocked.delivered_text


def test_invalid_timezone_fails_closed_for_relative_date_claim():
    result = validate_coach_narrative(
        "Сегодня понедельник.",
        _evidence(athlete_timezone="Mars/Olympus"),
    )

    assert result.outcome == "data_gap"
    assert result.reason_codes == ("INVALID_ATHLETE_TIMEZONE",)


def test_yesterday_weekday_must_match_athlete_calendar():
    result = validate_coach_narrative("Вчера был понедельник.", _evidence())

    assert result.outcome == "replaced"
    assert result.reason_codes == ("CALENDAR_REFERENCE_MISMATCH",)


def test_missed_session_without_canonical_plan_fact_evidence_is_refused():
    result = validate_coach_narrative(
        "Вчерашняя тренировка пропущена.",
        _evidence(session_evidence=None),
    )

    assert result.outcome == "data_gap"
    assert result.reason_codes == ("SESSION_MISSED_UNSUPPORTED",)


def test_explicit_did_not_start_fact_supports_missed_session_claim():
    raw = "Вчерашняя тренировка пропущена."
    session_evidence = {
        "status": "available",
        "date": "2026-08-23",
        "rule_version": "plan_fact_v1",
        "rows": [{"completion_status": "did_not_start"}],
    }

    result = validate_coach_narrative(
        raw,
        _evidence(session_evidence=session_evidence),
    )

    assert result.outcome == "pass"
    assert result.delivered_text == raw


@pytest.mark.parametrize(
    "raw",
    [
        "Сегодняшняя тренировка пропущена.",
        "Вчерашняя плавательная тренировка пропущена.",
    ],
)
def test_missed_session_evidence_must_match_claimed_date_and_sport(raw: str):
    session_evidence = {
        "status": "available",
        "date": "2026-08-23",
        "rule_version": "plan_fact_v1",
        "rows": [
            {
                "date": "2026-08-23",
                "session_id": "yesterday-run",
                "sport": "run",
                "completion_status": "did_not_start",
            }
        ],
    }

    result = validate_coach_narrative(
        raw,
        _evidence(session_evidence=session_evidence),
    )

    assert result.outcome == "data_gap"
    assert result.reason_codes == ("SESSION_MISSED_UNSUPPORTED",)


def test_today_projection_joins_real_feedback_completion_status(monkeypatch):
    from api import today_snapshot

    class FakeDb:
        def get_latest_planning_checkpoint(self):
            return {"id": 7}

        def get_latest_session_feedbacks(self):
            return [
                {
                    "session_id": "session-1",
                    "status": "active",
                    "completion_status": "did_not_start",
                    "rule_version": "session_feedback_v1",
                }
            ]

    monkeypatch.setattr(
        today_snapshot,
        "_yesterday_reconciliation",
        lambda *_args, **_kwargs: {
            "status": "available",
            "date": "2026-08-23",
            "rule_version": "plan_fact_v1",
            "rows": [{"session_id": "session-1", "match_status": "unmatched"}],
        },
    )

    evidence = today_snapshot.build_coach_session_evidence(
        FakeDb(),
        as_of=datetime(2026, 8, 24).date(),
    )

    assert evidence["rows"][0]["completion_status"] == "did_not_start"
    assert evidence["rows"][0]["feedback_rule_version"] == "session_feedback_v1"


def test_negation_intent_and_quoted_text_do_not_trigger_material_claims():
    raw = (
        "Ты не пропустил тренировку. Хочу улучшить HRV со временем.\n"
        "> В старом сообщении было: «восстановление плохое»."
    )

    result = validate_coach_narrative(raw, _evidence())

    assert result.outcome == "pass"
    assert result.delivered_text == raw


def test_intent_clause_does_not_hide_a_following_factual_claim():
    result = validate_coach_narrative(
        "Планирую снизить нагрузку, потому что восстановление плохое.",
        _evidence(),
    )

    assert result.outcome == "replaced"
    assert result.reason_codes == ("READINESS_CLAIM_CONTRADICTED",)


@pytest.mark.parametrize(
    "raw,reason_code",
    [
        ("**Восстановление** плохое.", "READINESS_CLAIM_CONTRADICTED"),
        ("HRV **подавлен**.", "HRV_CLAIM_CONTRADICTED"),
    ],
)
def test_inline_markdown_cannot_hide_a_material_claim(raw: str, reason_code: str):
    result = validate_coach_narrative(raw, _evidence())

    assert result.outcome == "replaced"
    assert result.reason_codes == (reason_code,)


def test_hrv_claim_rejects_stale_enclosing_readiness_snapshot():
    snapshot = _snapshot(status="limited", hrv_score=40.0)
    snapshot.update({"stale": True, "is_provisional": True})

    result = validate_coach_narrative(
        "HRV подавлен.",
        _evidence(readiness_snapshot=snapshot),
    )

    assert result.outcome == "data_gap"
    assert result.reason_codes == ("READINESS_EVIDENCE_STALE",)


@pytest.mark.parametrize(
    "raw",
    [
        "Данные не подтверждают, что восстановление плохое.",
        "Нельзя сказать, что HRV снижен.",
        "Держи нагрузку стабильной до следующей проверки.",
        "Сегодня держи нагрузку стабильной.",
        "Нагрузку держи стабильной.",
        "Если восстановление плохое, выбери лёгкую сессию.",
        "При плохом восстановлении выбери лёгкую сессию.",
        "При плохом восстановлении лучше отдохнуть.",
        "При плохом восстановлении отдыхай.",
        "Тренировка не пропущена.",
        "Тренировка не была пропущена.",
        "Тренировка выполнена, не пропущена.",
        "Фраза «HRV ниже нормы» здесь приведена как пример.",
    ],
)
def test_negated_evidence_and_advice_are_not_material_claims(raw: str):
    result = validate_coach_narrative(raw, _evidence())

    assert result.outcome == "pass"
    assert result.delivered_text == raw


@pytest.mark.parametrize(
    "raw,reason_code",
    [
        ("При этом восстановление плохое.", "READINESS_CLAIM_CONTRADICTED"),
        ("При текущих данных восстановление плохое.", "READINESS_CLAIM_CONTRADICTED"),
        ("Нагрузка растет, поэтому держи текущий объём.", "TREND_COMPARATOR_MISSING"),
        ("Форма ухудшается — сохраняй план.", "TREND_COMPARATOR_MISSING"),
        (
            "Эту тренировку ты не пропустил. Другая тренировка пропущена.",
            "SESSION_MISSED_UNSUPPORTED",
        ),
    ],
)
def test_assertion_is_not_hidden_by_an_unrelated_guard(raw: str, reason_code: str):
    result = validate_coach_narrative(raw, _evidence())

    assert result.outcome in {"replaced", "data_gap"}
    assert result.reason_codes == (reason_code,)


@pytest.mark.parametrize(
    "raw,reason_code",
    [
        ("Readiness низкая, нужен отдых.", "READINESS_CLAIM_CONTRADICTED"),
        ("Ты не восстановился.", "READINESS_CLAIM_CONTRADICTED"),
        ("Ты плохо восстановился.", "READINESS_CLAIM_CONTRADICTED"),
        ("Восстановление просело.", "READINESS_CLAIM_CONTRADICTED"),
        ("HRV ниже нормы.", "HRV_CLAIM_CONTRADICTED"),
        ("HRV просел.", "HRV_CLAIM_CONTRADICTED"),
    ],
)
def test_common_unsupported_recovery_phrasings_are_blocked(raw: str, reason_code: str):
    result = validate_coach_narrative(raw, _evidence())

    assert result.outcome == "replaced"
    assert result.reason_codes == (reason_code,)


@pytest.mark.parametrize("raw", ["Нагрузка выросла.", "Нагрузка снизилась."])
def test_common_load_trend_claims_require_a_comparator(raw: str):
    result = validate_coach_narrative(raw, _evidence())

    assert result.outcome == "data_gap"
    assert result.reason_codes == ("TREND_COMPARATOR_MISSING",)


@pytest.mark.parametrize(
    "tool_name,raw_result",
    [
        (
            "compare_periods",
            {
                "recent_period": {"no_data": False},
                "previous_period": {"no_data": False},
                "comparison": {"tss_change": -100.0},
            },
        ),
        (
            "analyze_training_load",
            {
                "weekly_breakdown": [{"total_tss": 300}, {"total_tss": 200}],
                "load_trend": "decreasing",
            },
        ),
        (
            "analyze_training_load",
            {
                "weekly_breakdown": [{"total_tss": 300}, {"total_tss": 200}],
                "load_trend": "снижение",
            },
        ),
    ],
)
def test_load_trend_direction_must_match_comparator(tool_name: str, raw_result: dict):
    result = validate_coach_narrative(
        "Нагрузка растет.",
        _evidence(
            tool_results=[
                {"tool_name": tool_name, "success": True, "raw_result": raw_result}
            ]
        ),
    )

    assert result.outcome == "replaced"
    assert result.reason_codes == ("TREND_CLAIM_CONTRADICTED",)


def test_reason_codes_have_stable_policy_order():
    result = validate_coach_narrative(
        "Восстановление плохое, HRV подавлен, тренд улучшается.",
        _evidence(),
    )

    assert result.reason_codes == (
        "READINESS_CLAIM_CONTRADICTED",
        "HRV_CLAIM_CONTRADICTED",
        "TREND_COMPARATOR_MISSING",
    )


def test_replacement_text_cannot_invert_the_decision_classifier():
    from models.coach_decisions import build_coach_decision

    gate_result = validate_coach_narrative("Восстановление плохое.", _evidence())
    decision = build_coach_decision(gate_result.delivered_text)

    assert gate_result.outcome == "replaced"
    assert decision.decision_type == "Monitor"


def test_shared_finalizer_fails_closed_when_evidence_builder_raises(monkeypatch):
    from models import ai_coach_runtime

    monkeypatch.setattr(
        ai_coach_runtime,
        "_runtime_narrative_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected")),
    )

    final = ai_coach_runtime.finalize_ai_chat_response(
        "Восстановление плохое.",
        ai_tools=None,
        tool_result_formatter=lambda _name, value: str(value),
    )

    assert "Восстановление плохое" not in final
    assert "Данных недостаточно" in final


def test_streaming_route_never_emits_unsafe_provider_text_and_audits_gate(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    from config.settings import Settings
    from data.database import Database

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod
    from models.chat_manager import ChatManager

    provider = object()
    turn_anchors: dict[str, object] = {}
    monkeypatch.setattr(coach_mod, "resolve_provider", lambda _kind=None: provider)
    monkeypatch.setattr(coach_mod, "supports_streaming", lambda _provider: True)
    monkeypatch.setattr(
        coach_mod,
        "resolve_turn_tool_results",
        lambda **_kwargs: {
            "rendered_response": "",
            "tool_results": [
                {
                    "tool_name": "get_readiness_today",
                    "success": True,
                    "raw_result": {"readiness": _snapshot()},
                    "formatted_result": "readiness 82",
                }
            ],
            "native": False,
        },
    )
    monkeypatch.setattr(
        coach_mod,
        "stream_tokens",
        lambda *_args, **_kwargs: iter(
            ["Восстановление плохое, ", "HRV подавлен — нужен отдых."]
        ),
    )
    def _readiness(_db, **kwargs):
        turn_anchors["readiness_as_of"] = kwargs.get("as_of")
        turn_anchors["readiness_observed_at"] = kwargs.get("observed_at_utc")
        return _snapshot()

    monkeypatch.setattr(coach_mod, "athlete_local_date", lambda _observed: date(2026, 8, 24))
    monkeypatch.setattr(coach_mod, "build_readiness_snapshot", _readiness)
    monkeypatch.setattr(
        coach_mod,
        "build_coach_session_evidence",
        lambda _db, **_kwargs: {"status": "empty", "rows": []},
    )
    monkeypatch.setattr(coach_mod, "get_active_plan", lambda _db: None)
    def _recovery(*_args, **kwargs):
        turn_anchors["recovery_today"] = kwargs.get("today")
        return {
            "outcome": "silence",
            "proposal": None,
            "readiness_conflicts": {"silence": True, "data_gap": False},
        }

    monkeypatch.setattr(coach_mod, "run_recovery_replan_loop", _recovery)

    db = Database(str(tmp_path / "coach.db"))
    response = coach_mod.coach_chat(
        coach_mod.ChatRequest(message="Как восстановление?", provider="mock"),
        db,
    )

    async def _collect(streaming_response) -> list[dict]:
        events = []
        async for raw in streaming_response.body_iterator:
            text = raw if isinstance(raw, str) else raw.decode()
            if text.startswith("data:"):
                events.append(json.loads(text[5:].strip()))
        return events

    events = asyncio.run(_collect(response))
    delivered = "".join(event["content"] for event in events if event["type"] == "token")
    done = events[-1]

    assert "Восстановление плохое" not in delivered
    assert "readiness 82" in delivered
    assert done["type"] == "done"
    assert done["evidence_gate"]["outcome"] == "replaced"
    assert done["evidence_gate"]["reason_codes"] == [
        "READINESS_CLAIM_CONTRADICTED",
        "HRV_CLAIM_CONTRADICTED",
    ]
    saved_messages = ChatManager().get_chat_messages(done["chat_id"])
    assert saved_messages[-1]["content"] == delivered
    decision = db.get_coach_decisions(days=30)[0]
    assert decision["decision_type"] == "Monitor"
    assert decision["narrative_gate_outcome"] == "replaced"
    assert decision["narrative_gate_reason_codes"] == done["evidence_gate"]["reason_codes"]
    assert decision["narrative_evidence_fingerprint"] == done["evidence_gate"][
        "evidence_fingerprint"
    ]
    assert turn_anchors["readiness_as_of"] == date(2026, 8, 24)
    assert turn_anchors["recovery_today"] == date(2026, 8, 24)
    assert getattr(turn_anchors["readiness_observed_at"], "tzinfo", None) is not None

    def _raise_builder(**_kwargs):
        raise RuntimeError("injected evidence builder failure")

    monkeypatch.setattr(coach_mod, "build_coach_narrative_evidence", _raise_builder)
    failed_response = coach_mod.coach_chat(
        coach_mod.ChatRequest(message="Повтори проверку", provider="mock"),
        db,
    )
    failed_events = asyncio.run(_collect(failed_response))
    failed_text = "".join(
        event["content"] for event in failed_events if event["type"] == "token"
    )

    assert "Восстановление плохое" not in failed_text
    assert "Данных недостаточно" in failed_text
    assert failed_events[-1]["type"] == "done"
    assert failed_events[-1]["evidence_gate"]["outcome"] == "data_gap"


def test_legacy_decision_schema_migrates_gate_metadata_additively(tmp_path):
    from data.database import Database

    db_path = tmp_path / "legacy-decisions.db"
    with sqlite3.connect(db_path) as conn:
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO coach_decisions
                (date, decision_type, reason, chat_id, message_id)
            VALUES ('2026-08-24T09:00:00Z', 'Monitor', 'legacy', 'chat-1', 'msg-1')
            """
        )

    db = Database(str(db_path))
    rows = db.get_coach_decisions(days=36500)

    assert rows[0]["narrative_gate_outcome"] is None
    assert rows[0]["narrative_gate_reason_codes"] == []
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(coach_decisions)")}
    assert {
        "narrative_gate_outcome",
        "narrative_gate_reason_codes_json",
        "narrative_gate_rule_version",
        "narrative_evidence_version",
        "narrative_evidence_fingerprint",
    } <= columns

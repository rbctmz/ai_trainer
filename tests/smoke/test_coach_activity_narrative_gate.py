"""Saved real-model counterexamples and scoped activity evidence boundaries."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from models.coach_narrative_evidence import build_coach_narrative_evidence, validate_coach_narrative

pytestmark = pytest.mark.smoke
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/coach_activity_narrative_cases.json"
REASON = "ACTIVITY_STRUCTURE_CLAIM_UNSUPPORTED"


def _saved(report="final", *, state="empty", repeat=1, variant=None):
    rows = json.loads(FIXTURES.read_text())["final" if report == "final" else "source"]
    return next(row for row in rows
                if row["repeat"] == repeat
                and (row.get("expected_structure_status") == state if report == "final"
                     else row["variant"] == variant))


def _evidence(tools):
    return build_coach_narrative_evidence(readiness_snapshot={}, tool_results=tools,
        athlete_timezone="Europe/Moscow", observed_at_utc=datetime(2026, 10, 15, tzinfo=timezone.utc))


@pytest.mark.parametrize("report,variant,repeat", [
    ("final", None, 1), ("source", "before", 1),
    ("source", "before", 2), ("source", "after", 1),
])
def test_saved_unsupported_assurances_are_not_deliverable(report, variant, repeat):
    row = _saved(report, variant=variant, repeat=repeat)
    evidence = _evidence(row["tool_results"])
    result = validate_coach_narrative(row["final_answer"], evidence)
    assert result.outcome == "replaced"
    assert REASON in result.reason_codes
    assert result.delivered_text != row["final_answer"]
    assert "это подтвердит" not in result.delivered_text.lower()
    assert "назову отрезки" not in result.delivered_text.lower()
    activity = row["tool_results"][0]["raw_result"]["activities"][0]
    assert activity["date"] in result.delivered_text
    assert str(activity["duration_minutes"]) in result.delivered_text
    assert validate_coach_narrative(result.delivered_text, evidence).outcome == "pass"


@pytest.mark.parametrize("state,repeat", [("unavailable", 1), ("unavailable", 2), ("structured", 1)])
def test_saved_supported_answers_are_preserved(state, repeat):
    row = _saved(state=state, repeat=repeat)
    result = validate_coach_narrative(row["final_answer"], _evidence(row["tool_results"]))
    assert result.outcome == "pass"
    assert result.delivered_text == row["final_answer"]


def test_saved_live_denial_passes_without_correction():
    from models.ai_coach_runtime import revalidate_with_correction
    row = json.loads(FIXTURES.read_text())["live"][0]
    original = row["answer_verification"]["initial_answer"]
    evidence = _evidence(row["tool_results"])
    gate = validate_coach_narrative(original, evidence)
    assert gate.outcome == "pass" and gate.delivered_text == original

    class NoCallProvider:
        def generate_response(self, *args, **kwargs):
            pytest.fail("supported denial must not request correction")
    delivered = revalidate_with_correction(provider=NoCallProvider(), gate_result=gate, evidence=evidence,
        history_messages=[], user_input=row["prompt"], tool_results=row["tool_results"])
    assert delivered.delivered_text == original and delivered.outcome == "pass"


@pytest.mark.parametrize("text", [
    "Гарантировать, что после этого отрезки появятся, не могу.",
    "Не могу гарантировать, что после этого отрезки появятся.",
    "Не могу гарантировать, что данные попадут в кэш и отрезки появятся.",
    "Гарантировать, что проверка карточки подтвердит гипотезу об отрезках, не могу.",
    "Не могу гарантировать, что проверка карточки подтвердит гипотезу об отрезках.",
    "Гарантировать, что после запроса назову отрезки, не могу.",
    "Не могу гарантировать, что после запроса назову отрезки.",
])
def test_explicit_guarantee_denial_is_preserved(text):
    result = validate_coach_narrative(text, _evidence(_saved(state="unavailable")["tool_results"]))
    assert result.outcome == "pass" and result.delivered_text == text


@pytest.mark.parametrize("text", [
    "После этого отрезки появятся.",
    "Гарантировать, что после этого отрезки появятся, могу.",
    "Не могу не гарантировать, что после этого отрезки появятся.",
    "Гарантировать, что после этого отрезки появятся, не могу не обещать.",
    "Не могу гарантировать, что отрезки появятся, но после синхронизации они появятся.",
    "Гарантировать, что отрезки появятся, не могу, но проверка карточки подтвердит гипотезу об отрезках.",
    "Не могу гарантировать, что отрезки появятся, а после открытия карточки они появятся.",
    "Не могу гарантировать, что отрезки появятся, и проверка карточки подтвердит гипотезу об отрезках.",
    "Не могу гарантировать исправность часов, но после синхронизации отрезки появятся.",
    "Не могу гарантировать, что отрезки появятся; повторите запрос — тогда назову отрезки.",
])
def test_denial_cannot_exempt_a_real_or_neighboring_guarantee(text):
    result = validate_coach_narrative(text, _evidence(_saved(state="unavailable")["tool_results"]))
    assert result.outcome == "replaced" and REASON in result.reason_codes


@pytest.mark.parametrize("state,text", [
    ("empty", "Анализ сохранённых данных не выявил отрезков. Проверка карточки может подтвердить или опровергнуть гипотезу."),
    ("empty", "Анализ не нашёл отрезков. Проверьте карточку активности, чтобы проверить гипотезу."),
    ("empty", "Не факт, что проверка карточки подтвердит гипотезу о разметке отрезков."),
    ("empty", "Нельзя утверждать, что проверка карточки подтвердит гипотезу об отрезках."),
    ("unavailable", "Структура недоступна. Если данные успешно получены в кэш и инструмент вернул отрезки, тогда назову отрезки."),
    ("unavailable", "Структура недоступна: в кэше нет данных об отрезках. Результат синхронизации не гарантирован."),
    ("unavailable", "Сейчас нет отрезков в кэше. Структура недоступна."),
    ("empty", "Нельзя утверждать, что сессия была лёгкой. Анализ не нашёл отрезков."),
    ("empty", "Если проверка карточки подтвердит гипотезу об отрезках, обсудим результат проверки."),
])
def test_conditional_verification_and_unknown_are_allowed(state, text):
    row = _saved(state=state)
    assert validate_coach_narrative(text, _evidence(row["tool_results"])).outcome == "pass"


@pytest.mark.parametrize("state,text", [
    ("unavailable", "Отрезков в тренировке не было."),
    ("empty", "Сессия прошла без интервалов."),
    ("unavailable", "Структура недоступна. После синхронизации интервалы появятся."),
    ("unavailable", "Повторите запрос — тогда назову отрезки."),
    ("empty", "Проверка карточки подтвердит гипотезу о разметке отрезков."),
    ("empty", "Сессия была лёгкой."),
    ("empty", "Тренировка прошла равномерно."),
])
def test_known_unsafe_forms_are_hard_rejections(state, text):
    result = validate_coach_narrative(text, _evidence(_saved(state=state)["tool_results"]))
    assert result.outcome == "replaced" and REASON in result.reason_codes


def test_evidence_allowlist_states_identity_conflicts_and_stable_order():
    rows = [_saved(state=state) for state in ("unavailable", "empty", "structured")]
    bundles = [_evidence(row["tool_results"]) for row in rows]
    assert len({bundle.fingerprint for bundle in bundles}) == 3
    tools = [deepcopy(row["tool_results"][0]) for row in rows]
    tools[0]["raw_result"]["activities"][0].update(message="private-key", unknown="secret", name="private-name")
    merged = _evidence(tools)
    assert merged.fingerprint == _evidence(list(reversed(tools))).fingerprint
    assert len(merged.payload["activity_structures"]) == 3
    assert "private-key" not in json.dumps(merged.payload) and "private-name" not in json.dumps(merged.payload)
    duplicate = deepcopy(tools[0])
    duplicate["raw_result"]["activities"][0]["structure_status"] = "empty"
    conflicted = _evidence([tools[0], duplicate]).payload["activity_structures"]
    assert len(conflicted) == 1 and conflicted[0]["structure_status"] == "unavailable"
    assert conflicted[0]["reason"] == "conflicting_evidence"
    failed = deepcopy(tools[0])
    failed["success"] = False
    malformed = deepcopy(tools[0])
    malformed["raw_result"]["activities"][0]["date"] = "not-a-date"
    assert _evidence([failed, malformed]).payload["activity_structures"] == []
    absent = validate_coach_narrative("Отрезков нет.", _evidence([failed, malformed]))
    assert absent.outcome == "replaced" and "Структура активности недоступна" in absent.delivered_text
    for state, mutation in (("empty", {"interval_count": False}),
                            ("structured", {"has_structure": False}),
                            ("structured", {"intervals": []})):
        invalid = deepcopy(_saved(state=state)["tool_results"])
        invalid[0]["raw_result"]["activities"][0].update(mutation)
        assert _evidence(invalid).payload["activity_structures"][0]["structure_status"] == "unavailable"


def test_mixed_dates_do_not_borrow_evidence_and_preserve_supported_intervals():
    tools = [deepcopy(_saved(state=state)["tool_results"][0]) for state in ("unavailable", "empty", "structured")]
    evidence = _evidence(tools)
    supported = "За 2026-10-13: два отрезка, 128 и 198 Вт.\nЗа 2026-10-14: структура недоступна.\nЗа 2026-10-12: анализ не нашёл отрезков."
    assert validate_coach_narrative(supported, evidence).outcome == "pass"
    for day in ("2026-10-14", "2026-10-13", "2026-10-11"):
        result = validate_coach_narrative(f"За {day}: отрезков нет.", evidence)
        assert result.outcome == "replaced", (day, result)
        assert "128" in result.delivered_text and "198" in result.delivered_text
    assert validate_coach_narrative("Проверка батареи подтвердит её заряд.", evidence).outcome == "pass"
    assert validate_coach_narrative("Завтра появится новая функция приложения.", evidence).outcome == "pass"
    assert validate_coach_narrative("Проверка карточки подтвердит гипотезу об отрезках.", _evidence([])).outcome == "pass"


def test_cache_condition_cannot_qualify_a_different_assertion():
    text = ("Если данные успешно получены в кэш и инструмент вернул отрезки, можно их назвать, "
            "но после открытия карточки новые интервалы появятся.")
    result = validate_coach_narrative(text, _evidence(_saved(state="unavailable")["tool_results"]))
    assert result.outcome == "replaced"


def test_explicit_activity_identity_survives_existing_markdown_normalization():
    tools = [deepcopy(_saved(state=state)["tool_results"][0]) for state in ("empty", "unavailable")]
    for tool, identity in zip(tools, ("empty_1", "missing_2")):
        tool["raw_result"]["activities"][0].update(activity_id=identity, date="2026-10-12")
    evidence = _evidence(tools)
    assert validate_coach_narrative("activity_id=empty_1: отрезков нет.", evidence).outcome == "pass"
    assert validate_coach_narrative("activity_id=missing_2: отрезков нет.", evidence).outcome == "replaced"


@pytest.mark.parametrize("state,text,expected", [
    ("structured", "Покажу отрезки из результата запроса: 11:00 при 128 Вт и 2:00 при 198 Вт.", "pass"),
    ("unavailable", "Можно проверить карточку активности, и эта проверка подтвердит гипотезу об отрезках.", "replaced"),
    ("unavailable", "Если данные получены в кэш, а инструмент не вернул отрезки, тогда назову отрезки.", "replaced"),
    ("unavailable", "Если данные получены в кэш и инструмент не подтвердил структуру, тогда назову отрезки.", "replaced"),
    ("unavailable", "Если данные успешно получены в кэш и инструмент get_activity_structure вернул отрезки, тогда назову отрезки.", "pass"),
    ("unavailable", "Если данные успешно получены в кэш и инструмент уже вернул отрезки, тогда назову отрезки.", "pass"),
    ("unavailable", "Если данные получены в кэш и инструмент get_activity_structure не вернул отрезки, тогда назову отрезки.", "replaced"),
])
def test_independent_review_claim_boundaries(state, text, expected):
    assert validate_coach_narrative(text, _evidence(_saved(state=state)["tool_results"])).outcome == expected


@pytest.mark.parametrize("response", [None, "", "Проверка карточки подтвердит гипотезу об отрезках.", "error"])
def test_one_shot_correction_failure_keeps_safe_factual_fallback(response):
    from models.ai_coach_runtime import revalidate_with_correction
    row = _saved()
    evidence = _evidence(row["tool_results"])
    rejected = validate_coach_narrative(row["final_answer"], evidence)

    class Provider:
        calls = 0
        def generate_response(self, prompt, system_prompt):
            self.calls += 1
            if response == "error":
                raise RuntimeError("offline failure")
            return response

    provider = Provider() if response is not None else None
    result = revalidate_with_correction(provider=provider, gate_result=rejected, evidence=evidence,
        history_messages=[], user_input="Какие отрезки?", tool_results=row["tool_results"])
    assert result.outcome == "replaced"
    assert provider is None or provider.calls == 1
    assert "40" in result.delivered_text and "6" in result.delivered_text
    assert "это подтвердит" not in result.delivered_text.lower()


def test_successful_correction_preserves_facts_and_metadata_shape():
    from models.ai_coach_runtime import revalidate_with_correction
    row = _saved()
    evidence = _evidence(row["tool_results"])
    rejected = validate_coach_narrative(row["final_answer"], evidence)
    corrected = "Анализ сессии не нашёл отрезков: 40 мин, 6 км. Проверка карточки может подтвердить или опровергнуть гипотезу."
    class Provider:
        def generate_response(self, prompt, system_prompt):
            assert "подтвердить или опровергнуть" in prompt
            return corrected
    result = revalidate_with_correction(provider=Provider(), gate_result=rejected, evidence=evidence,
        history_messages=[], user_input="Какие отрезки?", tool_results=row["tool_results"])
    assert result.outcome == "pass" and result.delivered_text == corrected
    metadata = result.metadata()
    assert set(metadata) == {"rule_version", "outcome", "reason_codes", "evidence_version", "evidence_fingerprint"}
    assert metadata["rule_version"] == "coach_narrative_gate_v4"
    assert metadata["evidence_version"] == "coach_narrative_evidence_v3"


def test_legacy_shared_finalizer_never_delivers_saved_unsafe_answer(tmp_path):
    from datetime import date
    from models.ai_coach_runtime import finalize_ai_chat_response
    from models.ai_tools import AITools
    from models.coach_tool_presenter import format_tool_result
    from tests.fixtures.coach_activity_cases import build_analyzed_empty_database

    database = build_analyzed_empty_database(tmp_path / "legacy.db", date(2026, 10, 12))
    unsafe = _saved()["final_answer"]
    delivered = finalize_ai_chat_response(
        "[TOOL: get_activity_structure, activity_id=syn-run-empty]\n" + unsafe,
        AITools(database), format_tool_result)
    assert "это подтвердит" not in delivered.lower()
    assert "2026-10-12" in delivered and "40" in delivered and "6" in delivered


def test_api_streams_and_persists_only_validated_activity_text(tmp_path, monkeypatch):
    import asyncio
    from config.settings import Settings
    from data.database import Database
    from api.routers import coach
    from models.chat_manager import ChatManager

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"))
    saved = _saved()
    class Provider:
        calls = 0
        def generate_response(self, prompt, system_prompt):
            self.calls += 1
            return saved["final_answer"]  # correction fails the same rule
    provider = Provider()
    monkeypatch.setattr(coach, "resolve_provider", lambda _kind=None: provider)
    monkeypatch.setattr(coach, "supports_streaming", lambda _provider: True)
    monkeypatch.setattr(coach, "resolve_turn_tool_results", lambda **kwargs: {
        "rendered_response": "", "tool_results": saved["tool_results"], "native": False})
    monkeypatch.setattr(coach, "stream_tokens", lambda *args, **kwargs: iter([saved["final_answer"]]))
    monkeypatch.setattr(coach, "build_readiness_snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(coach, "build_coach_session_evidence", lambda *args, **kwargs: {"status": "empty", "rows": []})
    monkeypatch.setattr(coach, "_load_coach_plan_boundary", lambda _db: (None, None))
    monkeypatch.setattr(coach, "run_recovery_replan_loop", lambda *args, **kwargs: {
        "outcome": "silence", "proposal": None, "readiness_conflicts": {"silence": True, "data_gap": False}})
    database = Database(str(tmp_path / "api.db"))
    response = coach.coach_chat(coach.ChatRequest(message="Какие отрезки?", provider="mock"), database)
    async def collect():
        events = []
        async for item in response.body_iterator:
            text = item if isinstance(item, str) else item.decode()
            if text.startswith("data:"):
                events.append(json.loads(text[5:].strip()))
        return events
    events = asyncio.run(collect())
    delivered = "".join(event["content"] for event in events if event["type"] == "token")
    done = events[-1]
    assert done["type"] == "done", done
    assert provider.calls == 1
    assert "это подтвердит" not in delivered.lower()
    assert "40" in delivered and "6" in delivered
    assert done["evidence_gate"]["reason_codes"] == [REASON]
    assert done["evidence_gate"]["rule_version"] == "coach_narrative_gate_v4"
    assert ChatManager().get_chat_messages(done["chat_id"])[-1]["content"] == delivered

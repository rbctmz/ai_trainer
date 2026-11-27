"""Source-bound import turns never run ordinary Coach writes or trust AI status."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from openai import APIStatusError
import pytest

from api.deps import get_database
from api.routers import coach
from data.database import Database
from data import swim_import_store as drafts
from data import swim_program_store as library
from models.ai_providers import DeepSeekProvider, DeepSeekResponsesProvider
from tests.smoke.test_swim_import_store import capture, content, parse
from api.swim_coach_contract import SwimCoachTurnRequest

pytestmark = pytest.mark.smoke


class Provider:
    def __init__(self, rounds=()):
        self.rounds = list(rounds)
        self.calls = []

    def supports_native_tools(self):
        return True

    def generate_with_tools(self, messages, tools, system_prompt=""):
        self.calls.append((deepcopy(messages), deepcopy(tools), system_prompt))
        if self.rounds:
            result = self.rounds.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return {"text": "SAVED AND SENT PRIVATE_CANARY", "tool_calls": []}


def call(name, arguments):
    return {
        "text": "",
        "tool_calls": [{"id": "call1", "name": name, "arguments": arguments}],
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"))
    db = Database(str(tmp_path / "coach.sqlite"))
    app = FastAPI()
    app.include_router(coach.router)
    app.dependency_overrides[get_database] = lambda: db

    def forbid(*args, **kwargs):
        raise AssertionError("ordinary planning/recovery path entered")

    monkeypatch.setattr(coach, "run_recovery_replan_loop", forbid)
    monkeypatch.setattr(coach, "current_plan_snapshot", forbid)
    monkeypatch.setattr(coach, "_load_metrics_context", forbid)
    monkeypatch.setattr(db, "save_coach_proposal", forbid)
    with TestClient(app) as client:
        yield client, db, tmp_path


def request(draft, **values):
    return {
        "message": "Interpret the retained source",
        "import_id": draft["import_id"],
        "expected_revision": draft["revision"],
        "request_id": str(uuid4()),
        **values,
    }


def events(response):
    assert response.status_code == 200, response.text
    return [
        json.loads(line[5:].strip())
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]


@pytest.mark.parametrize("provider_class", [DeepSeekProvider, DeepSeekResponsesProvider])
@pytest.mark.parametrize(
    "http_status, code, message",
    [
        (402, "swim_coach_provider_payment_required", "недостаточно средств"),
        (503, "swim_coach_provider_failed", "Провайдер ИИ не смог обработать запрос"),
    ],
)
def test_provider_http_failure_has_safe_reason(setup, monkeypatch, provider_class, http_status, code, message):
    client, db, _ = setup
    empty = capture(db)
    response = httpx.Response(http_status, request=httpx.Request("POST", "https://provider.invalid"))

    def rejected(**kwargs):
        raise APIStatusError("PRIVATE_CANARY", response=response, body=None)

    settings = SimpleNamespace(
        DEEPSEEK_API_KEY=None,
        DEEPSEEK_MODEL="offline",
        DEEPSEEK_BASE_URL="https://provider.invalid",
        AI_RESPONSE_MAX_TOKENS=256,
        AI_TOOLS_TEMPERATURE=0,
    )
    provider = provider_class(settings=settings)
    provider.api_key = "offline-only"
    endpoint = SimpleNamespace(create=rejected)
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=endpoint), responses=endpoint)
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)

    reply = client.post("/api/coach/swim-import", json=request(empty))
    out = events(reply)
    update = next(event for event in out if event["type"] == "swim_import")
    assert (update["status"], update["code"], update["revision"]) == ("error", code, 0)
    assert any(message in event["content"] for event in out if event["type"] == "token")
    assert "PRIVATE_CANARY" not in reply.text
    assert drafts.get_draft(db, empty["import_id"])["revision"] == 0


def test_text_only_reply_explains_that_no_parse_started(setup, monkeypatch):
    client, db, _ = setup
    empty = capture(db)
    # Text resembling an SDK failure must not be interpreted as provider metadata.
    provider = Provider([{"text": "Ошибка HTTP 402 PRIVATE_CANARY", "tool_calls": []}])
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)

    reply = client.post("/api/coach/swim-import", json=request(empty))
    out = events(reply)
    update = next(event for event in out if event["type"] == "swim_import")
    assert (update["status"], update["code"], update["revision"]) == ("unparsed", "swim_coach_no_change", 0)
    assert any("не запустил разбор" in event["content"] for event in out if event["type"] == "token")
    assert "PRIVATE_CANARY" not in reply.text


def test_provider_failure_after_parse_reports_committed_draft(setup, monkeypatch):
    client, db, _ = setup
    empty = capture(db)
    provider = Provider([
        call("parse_swim_import", {"content": content()}),
        {"text": "PRIVATE_CANARY", "tool_calls": [], "provider_error": "payment_required"},
    ])
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)

    reply = client.post("/api/coach/swim-import", json=request(empty))
    out = events(reply)
    update = next(event for event in out if event["type"] == "swim_import")
    assert update["code"] == "swim_coach_provider_payment_required"
    assert update["revision"] == 1 and update["readback_status"] == "current"
    assert any(event["type"] == "tool_call" and event["status"] == "done" for event in out)
    assert any("Черновик уже обновился" in event["content"] for event in out if event["type"] == "token")
    assert "PRIVATE_CANARY" not in reply.text
    assert drafts.get_draft(db, empty["import_id"])["revision"] == 1


def test_http_parse_emits_one_whole_draft_and_no_false_saved_status(setup, monkeypatch):
    client, db, root = setup
    empty = capture(db)
    provider = Provider([call("parse_swim_import", {"content": content()})])
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)
    result = client.post("/api/coach/swim-import", json=request(empty))
    out = events(result)
    updates = [e for e in out if e["type"] == "swim_import"]
    assert (
        len(updates) == 1
        and updates[0]["revision"] == 1
        and updates[0]["status"] == "draft"
    )
    assert "SAVED AND SENT" not in result.text and "PRIVATE_CANARY" not in result.text
    assert not any(e["type"] == "proposal" for e in out)
    assert out[-1]["type"] == "done" and out[-1]["revision"] == 1
    assert drafts.get_draft(db, empty["import_id"])["actor"] == "coach"
    assert library.list_programs(db) == []
    chat_id = out[0]["chat_id"]
    chat = json.loads((root / "chats" / f"{chat_id}.json").read_text())
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant"]
    assert "PRIVATE_CANARY" not in chat["messages"][-1]["content"]


def test_no_provider_unsupported_marker_and_stale_turn_fail_before_call(
    setup, monkeypatch
):
    client, db, _ = setup
    empty = capture(db)
    monkeypatch.setattr(coach, "resolve_provider", lambda _: None)
    result = client.post("/api/coach/swim-import", json=request(empty))
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "swim_coach_provider_unavailable"
    assert drafts.get_draft(db, empty["import_id"]) == empty
    provider = Provider()
    provider.supports_native_tools = lambda: False
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)
    result = client.post("/api/coach/swim-import", json=request(empty))
    assert (
        result.status_code == 422
        and result.json()["detail"]["code"] == "swim_coach_native_required"
    )
    assert provider.calls == []
    parse(db, empty)

    def never_resolve(_):
        raise AssertionError("stale turn reached provider resolution")

    monkeypatch.setattr(coach, "resolve_provider", never_resolve)
    assert client.post("/api/coach/swim-import", json=request(empty)).status_code == 409


@pytest.mark.parametrize(
    "rounds,revision",
    [
        ([call("parse_swim_import", {})], 0),
        ([call("create_plan_constraint", {"source_text": "PRIVATE_CANARY"})], 0),
        ([RuntimeError("PRIVATE_CANARY secret provider response")], 0),
        (
            [
                call("parse_swim_import", {"content": content()}),
                RuntimeError("PRIVATE_CANARY"),
            ],
            1,
        ),
    ],
)
def test_failed_or_partial_turn_has_safe_readback_and_no_false_success(
    setup, monkeypatch, rounds, revision
):
    client, db, _ = setup
    empty = capture(db)
    provider = Provider(rounds)
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)
    result = client.post("/api/coach/swim-import", json=request(empty))
    out = events(result)
    update = next(e for e in out if e["type"] == "swim_import")
    assert update["status"] == "error" and update["revision"] == revision
    assert "PRIVATE_CANARY" not in result.text and "SAVED AND SENT" not in result.text
    assert drafts.get_draft(db, empty["import_id"])["revision"] == revision
    assert library.list_programs(db) == []


def test_clarification_and_validation_keep_source_available(setup, monkeypatch):
    client, db, _ = setup
    empty = capture(db)
    provider = Provider(
        [call("ask_swim_import_question", {"question": "Which side first?"})]
    )
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)
    result = client.post("/api/coach/swim-import", json=request(empty))
    assert "Which side first?" in result.text
    assert (
        next(e for e in events(result) if e["type"] == "swim_import")["status"]
        == "unparsed"
    )
    assert drafts.get_draft(db, empty["import_id"]) == empty
    for extra in (
        {"actor": "user"},
        {"source_text": "PRIVATE_CANARY"},
        {"expected_revision": True},
        {"chat_id": "../PRIVATE_CANARY"},
    ):
        bad = client.post("/api/coach/swim-import", json=request(empty, **extra))
        assert (
            bad.status_code == 422
            and "PRIVATE_CANARY" not in bad.text
            and '"input"' not in bad.text
        )


def test_populated_typescript_swim_turn_contract(setup, monkeypatch):
    from tests.contracts.conformance import validate
    from tests.smoke.test_contract_extractor import _run_extractor

    artifact = _run_extractor(
        Path(__file__).resolve().parents[2] / "web/lib/types.ts",
        ["SwimCoachTurnRequest", "SwimCoachEvent"],
    )
    client, db, _ = setup
    empty = capture(db)
    monkeypatch.setattr(
        coach,
        "resolve_provider",
        lambda _: Provider([call("parse_swim_import", {"content": content()})]),
    )
    payload = request(empty)
    assert SwimCoachTurnRequest.model_validate(payload).expected_revision == 0
    assert (
        validate(payload, artifact["types"]["SwimCoachTurnRequest"], artifact["types"])
        == []
    )
    for event in events(client.post("/api/coach/swim-import", json=payload)):
        assert (
            validate(event, artifact["types"]["SwimCoachEvent"], artifact["types"])
            == []
        )


def test_three_workouts_stay_one_program_and_chat_continues_same_draft(
    setup, monkeypatch
):
    from tests.smoke._swim_import_fixtures import exact_program_v2

    client, db, _ = setup
    raw = exact_program_v2()
    empty = capture(db, raw["source_text"])
    initial = {key: raw[key] for key in ("title", "source_spans", "workouts")}
    monkeypatch.setattr(
        coach,
        "resolve_provider",
        lambda _: Provider([call("parse_swim_import", {"content": initial})]),
    )
    first = events(client.post("/api/coach/swim-import", json=request(empty)))
    draft = drafts.get_draft(db, empty["import_id"])
    assert [w["distance_meters"] for w in draft["summary"]["workouts"]] == [
        2200,
        2000,
        1900,
    ]
    assert draft["summary"]["distance_meters"] == 6100
    assert len([e for e in first if e["type"] == "swim_import"]) == 1
    original = deepcopy(draft["document"])
    monkeypatch.setattr(
        coach,
        "resolve_provider",
        lambda _: Provider(
            [
                call(
                    "patch_swim_import",
                    {"operation": {"op": "set_title", "title": "User-reviewed title"}},
                )
            ]
        ),
    )
    second = events(
        client.post(
            "/api/coach/swim-import",
            json=request(
                draft, chat_id=first[0]["chat_id"], message="Change only title"
            ),
        )
    )
    assert second[0]["chat_id"] == first[0]["chat_id"]
    expected = deepcopy(original)
    expected["title"] = "User-reviewed title"
    assert drafts.get_draft(db, empty["import_id"])["document"] == expected
    assert library.list_programs(db) == []


def test_demo_context_never_resolves_real_source(tmp_path, monkeypatch):
    from api import deps
    from api.routers.swim_imports import router as imports_router
    from config.settings import Settings
    from tests.smoke._swim_import_fixtures import SOURCE

    monkeypatch.setattr(Settings, "DATABASE_PATH", str(tmp_path / "real.sqlite"))
    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"))
    monkeypatch.setattr(deps, "DEMO_DB_PATH", str(tmp_path / "demo.sqlite"))
    deps._reset_db_cache()
    provider = Provider([call("parse_swim_import", {"content": content()})])
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)
    app = FastAPI()
    app.include_router(imports_router)
    app.include_router(coach.router)
    try:
        with TestClient(app) as client:
            empty = client.post(
                "/api/swim-imports?demo=1",
                json={"source_text": SOURCE, "request_id": str(uuid4())},
            ).json()
            assert (
                client.post("/api/coach/swim-import", json=request(empty)).status_code
                == 404
            )
            assert provider.calls == []
            demo = events(
                client.post("/api/coach/swim-import?demo=1", json=request(empty))
            )
            assert demo[-1]["revision"] == 1
            assert client.get("/api/swim-imports").json() == {"items": []}
            assert (
                client.get(f"/api/swim-imports/{empty['import_id']}?demo=1").json()[
                    "revision"
                ]
                == 1
            )
    finally:
        deps._reset_db_cache()


def test_chat_failure_after_tool_write_keeps_truthful_draft_readback(
    setup, monkeypatch
):
    from models.chat_manager import ChatManager

    client, db, _ = setup
    empty = capture(db)
    provider = Provider([call("parse_swim_import", {"content": content()})])
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)

    class FailingAssistantHistory(ChatManager):
        def add_message(self, chat_id, role, content):
            if role == "assistant":
                raise OSError("PRIVATE_CANARY storage diagnostic")
            return super().add_message(chat_id, role, content)

    monkeypatch.setattr(coach, "_chat_manager", FailingAssistantHistory)
    result = client.post("/api/coach/swim-import", json=request(empty))
    update = next(e for e in events(result) if e["type"] == "swim_import")
    assert update["status"] == "error" and update["revision"] == 1
    assert update["code"] == "swim_coach_history_unavailable"
    assert drafts.get_draft(db, empty["import_id"])["revision"] == 1
    assert "PRIVATE_CANARY" not in result.text and library.list_programs(db) == []


def test_missing_chat_corrupt_source_and_unavailable_provider_stop_before_call(
    setup, monkeypatch
):
    client, db, _ = setup
    empty = capture(db)
    provider = Provider()
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)
    assert (
        client.post(
            "/api/coach/swim-import", json=request(empty, chat_id="missing-chat")
        ).status_code
        == 404
    )
    assert provider.calls == []
    provider.is_available = lambda: False
    assert client.post("/api/coach/swim-import", json=request(empty)).status_code == 503
    assert provider.calls == []
    with db._connect() as conn:
        conn.execute("UPDATE swim_import_sources SET source_text='PRIVATE_CANARY'")
    response = client.post("/api/coach/swim-import", json=request(empty))
    assert response.status_code == 503 and "PRIVATE_CANARY" not in response.text
    assert provider.calls == []


@pytest.mark.parametrize("channel", ["question", "unresolved"])
def test_unverified_saved_claim_cannot_enter_structured_questions(
    setup, monkeypatch, channel
):
    client, db, root = setup
    empty = capture(db)
    claim = "Программа сохранена в библиотеку и отправлена на часы. Хотите продолжить?"
    if channel == "question":
        round1 = call("ask_swim_import_question", {"question": claim})
    else:
        raw = content()
        raw["workouts"][0]["steps"] = [
            {
                "kind": "unresolved",
                "id": "unknown",
                "instructions": "Original ambiguity",
                "question": claim,
            }
        ]
        round1 = call("parse_swim_import", {"content": raw})
    monkeypatch.setattr(coach, "resolve_provider", lambda _: Provider([round1]))
    response = client.post("/api/coach/swim-import", json=request(empty))
    out = events(response)
    assert claim not in response.text
    assert next(e for e in out if e["type"] == "swim_import")["status"] == "error"
    chat = json.loads((root / "chats" / f"{out[0]['chat_id']}.json").read_text())
    assert claim not in chat["messages"][-1]["content"]
    assert drafts.get_draft(db, empty["import_id"])["revision"] == 0
    assert library.list_programs(db) == []


def test_failed_final_readback_preserves_last_confirmed_revision(setup, monkeypatch):
    client, db, _ = setup
    empty = capture(db)
    real_get = drafts.get_draft

    def final_read_failure(*args, **kwargs):
        raise drafts.SwimImportError("storage_unavailable", 503)

    class PartialProvider(Provider):
        def generate_with_tools(self, messages, tools, system_prompt=""):
            if self.calls:
                monkeypatch.setattr(drafts, "get_draft", final_read_failure)
            return super().generate_with_tools(messages, tools, system_prompt)

    provider = PartialProvider([call("parse_swim_import", {"content": content()})])
    monkeypatch.setattr(coach, "resolve_provider", lambda _: provider)
    out = events(client.post("/api/coach/swim-import", json=request(empty)))
    actual = real_get(db, empty["import_id"])
    assert actual["revision"] == 1
    for event in out:
        if event["type"] in ("swim_import", "done"):
            assert event["revision"] == 1
            assert event["readback_status"] == "unavailable"


def test_old_draft_question_claim_is_filtered_from_narrative(setup, monkeypatch):
    client, db, _ = setup
    empty = capture(db)
    raw = content()
    claim = "Workout saved and sent. Continue?"
    raw["workouts"][0]["steps"] = [
        {
            "kind": "unresolved",
            "id": "unknown",
            "instructions": "Source ambiguity",
            "question": claim,
        }
    ]
    existing = parse(db, empty, **raw)
    monkeypatch.setattr(coach, "resolve_provider", lambda _: Provider())
    response = client.post("/api/coach/swim-import", json=request(existing))
    out = events(response)
    assert claim not in response.text
    update = next(e for e in out if e["type"] == "swim_import")
    assert (
        update["status"] == "error" and update["code"] == "swim_coach_unverified_claim"
    )
    assert drafts.get_draft(db, empty["import_id"]) == existing

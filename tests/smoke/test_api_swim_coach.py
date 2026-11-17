"""Source-bound import turns never run ordinary Coach writes or trust AI status."""

from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.deps import get_database
from api.routers import coach
from data.database import Database
from data import swim_import_store as drafts
from data import swim_program_store as library
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

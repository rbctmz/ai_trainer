"""Bounded native Coach authority over a retained source, without model calls."""

from copy import deepcopy
from uuid import uuid4

import pytest

from data.database import Database
from data import swim_import_store as drafts
from data import swim_program_store as library
from models.swim_coach_tools import SwimCoachTools
from tests.smoke.test_swim_import_store import capture, content, parse
from models.ai_coach_runtime import run_native_tool_loop

pytestmark = pytest.mark.smoke


def adapter(db, draft):
    return SwimCoachTools(
        db,
        import_id=draft["import_id"],
        expected_revision=draft["revision"],
        request_id=str(uuid4()),
    )


def test_source_and_actor_cannot_be_model_arguments_and_no_save_authority(tmp_path):
    db = Database(str(tmp_path / "authority.sqlite"))
    empty = capture(db)
    tools = adapter(db, empty)
    for forbidden in (
        "confirm_preview",
        "save_swim_program",
        "propose_plan_build",
        "create_plan_constraint",
        "prepare_swim_import",
    ):
        assert not tools.execute_tool(forbidden)["success"]
    for extra in (
        {"source_text": "PRIVATE_CANARY"},
        {"import_id": str(uuid4())},
        {"actor": "user"},
    ):
        result = tools.execute_tool("parse_swim_import", content=content(), **extra)
        assert not result["success"] and "PRIVATE_CANARY" not in str(result)
    assert drafts.get_draft(db, empty["import_id"]) == empty
    assert library.list_programs(db) == []


def test_initial_parse_and_one_pause_edit_use_same_persisted_draft(tmp_path):
    db = Database(str(tmp_path / "edit.sqlite"))
    empty = capture(db)
    raw = content()
    raw["workouts"][0]["steps"].append(
        {
            "kind": "rest",
            "id": "pause",
            "mode": "approximate",
            "seconds": {"minimum": 60, "maximum": 70},
        }
    )
    tools = adapter(db, empty)
    result = tools.execute_tool("parse_swim_import", content=raw)
    assert result["success"] and result["result"]["revision"] == 1
    first = drafts.get_draft(db, empty["import_id"])
    assert first["actor"] == "coach"
    assert tools.execute_tool("parse_swim_import", content=raw) == result
    refused = tools.execute_tool(
        "patch_swim_import",
        operation={"op": "set_title", "title": "Unexpected second write"},
    )
    assert not refused["success"] and refused["error"] == "swim_coach_mutation_limit"
    tools = adapter(db, first)
    old = deepcopy(first["document"])
    operation = {
        "op": "set_rest",
        "node_id": "pause",
        "mode": "open",
        "breaths": {"minimum": 3, "maximum": 4},
    }
    changed = tools.execute_tool("patch_swim_import", operation=operation)
    assert changed["success"] and changed["result"]["revision"] == 2
    expected = deepcopy(old)
    expected["workouts"][0]["steps"][-1].update(
        mode="open", seconds=None, breaths={"minimum": 3, "maximum": 4}
    )
    assert drafts.get_draft(db, empty["import_id"])["document"] == expected
    assert library.list_programs(db) == []


def test_human_ack_invalid_args_and_stale_write_fail_safely(tmp_path):
    db = Database(str(tmp_path / "fail.sqlite"))
    empty = capture(db)
    tools = adapter(db, empty)
    for kwargs in ({}, {"content": {"PRIVATE_CANARY": "secret"}}):
        result = tools.execute_tool("parse_swim_import", **kwargs)
        assert not result["success"] and "PRIVATE_CANARY" not in str(result)
    first = parse(db, empty)
    result = tools.execute_tool("parse_swim_import", content=content())
    assert not result["success"] and result["error"] == "swim_import_stale"
    assert drafts.get_draft(db, empty["import_id"]) == first
    tools = adapter(db, first)
    result = tools.execute_tool(
        "patch_swim_import",
        operation={
            "op": "acknowledge_source",
            "span": {"start": 0, "end": 1},
            "reason": "Model cannot acknowledge",
        },
    )
    assert not result["success"]


def test_tool_schema_has_all_refs_and_excludes_context_and_human_operations(tmp_path):
    db = Database(str(tmp_path / "schemas.sqlite"))
    tools = adapter(db, capture(db))
    schemas = tools.get_tool_schemas()
    assert {s["name"] for s in schemas} == {
        "get_swim_import",
        "search_swim_exercises",
        "get_swim_exercise",
        "get_swim_program",
        "parse_swim_import",
        "patch_swim_import",
        "ask_swim_import_question",
    }
    for schema in schemas:
        root = schema["parameters"]
        assert (
            not {"source_text", "import_id", "actor", "request_id", "expected_revision"}
            & root.get("properties", {}).keys()
        )

        def walk(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    target = root
                    for token in value["$ref"].split("/")[1:]:
                        target = target[token.replace("~1", "/").replace("~0", "~")]
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(root)
        assert "acknowledge_source" not in str(root)


def test_actual_native_loop_carries_nested_content_under_source_prompt(tmp_path):
    db = Database(str(tmp_path / "native.sqlite"))
    empty = capture(db)
    tools = adapter(db, empty)

    class Provider:
        def __init__(self):
            self.calls = []

        def generate_with_tools(self, messages, schemas, *, system_prompt):
            self.calls.append((deepcopy(messages), deepcopy(schemas), system_prompt))
            if len(self.calls) == 1:
                return {
                    "text": "",
                    "tool_calls": [
                        {
                            "id": "call1",
                            "name": "parse_swim_import",
                            "arguments": {"content": content()},
                        }
                    ],
                }
            return {"text": "SAVED AND SENT", "tool_calls": []}

    provider = Provider()
    text, results = run_native_tool_loop(
        provider,
        tools,
        "Interpret source",
        [],
        lambda name, value: str(value),
        system_prompt_override=tools.system_prompt(),
    )
    assert (
        text == "SAVED AND SENT"
    )  # Runtime text is untrusted; HTTP rendering is tested separately.
    assert len(results) == 1 and results[0]["success"]
    assert len(provider.calls) == 2
    assert empty["source_text"] in provider.calls[0][2]
    assert (
        drafts.get_draft(db, empty["import_id"])["document"]["workouts"][0]["steps"][1][
            "repeat"
        ]["finish"]
        == "current_cycle"
    )
    assert library.list_programs(db) == []
